from bs4 import BeautifulSoup
from selenium import webdriver
import time
import re
from urllib import request
import os


driver = webdriver.PhantomJS(executable_path=r'phantomjs_2_1_1' + os.path.sep + 'bin' + os.path.sep + 'phantomjs.exe')
driver.set_window_size(1920, 1080)
sleep_time = 0


class Crawler:
    name_for_file = 0
    store_dir = ""
    base_url = ""
    file_name = ""

    def __init__(self, url, file_name, store_dir):
        self.store_dir = store_dir
        self.base_url = url
        self.file_name = file_name

    def get_page(self, url):
        driver.get(url)
        time.sleep(sleep_time)
        return BeautifulSoup(driver.page_source)

    def write_file(self, file_path, file_content, type):
        f = open(file_path, type)
        f.write(file_content)
        f.close()

    def code_to_list(self, code):
        result = []
        count = 0
        for line in code.split('\n'):
            result.append((line + '\n', count))
            count = count + 1
        return result

    # 从最终版本的网页上抽取文件最终版本内容#
    def extract_source_file(self, page):
        table_content = page.findAll("table", {"class": "FileContents"})[0]
        if not table_content:
            return
        result = ""
        line_count = 0
        for td in table_content.findAll("td", {"class": "FileContents-lineContents"}):
            spans = td.findAll("span")
            line = ""
            for span in spans:
                line += span.text
            line += "\n"
            result += line
            line_count += 1
        print(line_count)

        self.write_file(self.store_dir + os.path.sep + 'sourcecode.txt', result, 'w')
        return result

    def find_issue(self, msg):
        obj = re.match(r'SOLR-([0-9]+)', msg)
        if obj:
            return 'https://issues.apache.org/jira/browse/' + obj.group()
        obj = re.match(r'LUCENE-([0-9]+)', msg)
        if obj:
            return 'https://issues.apache.org/jira/browse/' + obj.group()
        return

    # 提取commit的message信息
    def extract_commit_msg(self, page):
        message = page.find('pre', {'class': 'u-pre u-monospace MetadataMessage'}).text
        message = message[0: message.find("git-svn-id")]
        message = message.strip()

        issue_url = self.find_issue(message)
        if issue_url:
            message += ('[' + issue_url + ']')

        return message

    # 该方法从url中抽取diff信息
    # 返回数据类型为一个二元元组，第0个元素为message信息，第1个元素为diff信息。
    def extract_diff(self, url, file_name):
        diffs = []
        page = self.get_page(url)

        #抽取message信息
        message = self.extract_commit_msg(page)

        # 抽取diff信息
        for pre in page.findAll("pre", {"class": "u-pre u-monospace Diff"}):
            # 1是原文件，2是修改后的文件
            name = pre.findAll('a')[-1].text
            # name是以a/ 或b/ 开头
            if name[2:] == file_name:  # 找到文件
                diff_pre = pre.next_sibling
                hunk = ""
                change = ""
                for span in diff_pre.findAll("span"):
                    span_type = span["class"][0]
                    if span_type == "Diff-hunk":
                        if change:
                            diffs.append((hunk, change))
                            change = ""
                        hunk = span.text
                    elif span_type == 'Diff-change' or span_type == 'Diff-delete' or span_type == 'Diff-insert':
                        change += span.text + "\n"
                    else:
                        print("diff行还有其他种类" + span_type + ":" + url)
                diffs.append((hunk, change))
                break

        diff_str = message + '\n'
        for i in range(0, len(diffs)):
            diff_str += diffs[i][0]
            diff_str += diffs[i][1]
        self.write_file(self.store_dir + os.path.sep + str(self.name_for_file) + '.txt', diff_str, 'w')

        self.name_for_file += 1
        return message, diffs

    def extract_name(self, text):
        name = text[len('[Renamed from '): -1 * len(' - diff]')]
        return name

    # 函数参数中url是指向一次提交的页面，在该页面中包含了本次提交中涉及到的所有修改文件
    # 该方法实现的功能是从该列表中找到需要文件的diff信息的url，并从该diff url提取diff信息
    # url: 某次提交的地址
    # file_name: 带查找文件的文件名
    def extract_file(self, url, file_name):
        ori_file_name = ''
        page = self.get_page(url)
        ul = page.find("ul", {"class": "DiffTree"})
        diffs = ()
        for li in ul.findAll("li"):
            name = li.find("a").text
            if name == file_name:
                commit_type = li.find("span")["class"][1]
                url = 'https://apache.googlesource.com' + li.find('span').find('a')["href"]
                if commit_type == 'DiffTree-action--modify':
                    ori_file_name = file_name
                elif commit_type == 'DiffTree-action--rename':
                    ori_file_name = self.extract_name(li.find("span").text)
                elif commit_type == 'DiffTree-action--add':
                    ori_file_name = ""
                else:
                    print("还有其他的文件修改模式" + type + ":" + url)

                diffs = self.extract_diff(url, file_name)
                # ori_file_name为本次提交之前文件的名称, file_name为本次提交之后文件的名称
                # 只有在重命名时，两者会不一致
                # diffs[0]为massage信息， diffs[1]为diff信息

        return ori_file_name, file_name, diffs[0], diffs[1]


    # 获取一个文件的commit历史信息
    # url:指向一个文件的log页面，此页面上有该文件修改该文件的commit列表
    # file_name：制定待查找的文件名
    def scan_history(self, url, file_name):
        page = self.get_page(url)
        histories = []
        count = 0
        for li in page.findAll('li', "CommitLog-item CommitLog-item--default"):
            url = 'https://apache.googlesource.com' + li.find('a', {'class': 'u-sha1 u-monospace CommitLog-sha1'})['href']
            print(url)

            info = self.extract_file(url, file_name)
            file_name = info[0]
            histories.append((info[2], info[3]))
            count += 1
            if file_name == '':
                break

        return histories

    def diff_convert(self, diff):
        obj = re.match(r'@@ -([0-9]+),[0-9]+ \+([0-9]+),[0-9]+ @@', diff[0])
        former_position = int(obj.group(1))
        latter_position = int(obj.group(2))

        former = []
        latter = []
        for line in diff[1].split('\n'):
            try:
                if len(line) == 0:
                    break
                elif line[0] == '+':
                    latter.append((line[1:] + "\n", 1))
                elif line[0] == '-':
                    former.append((line[1:] + '\n', -1))
                else:
                    latter.append((line[1:] + '\n', 0))
                    former.append((line[1:] + '\n', 0))
            except:
                print("error:" + line)

        return former_position, former, latter_position, latter

    def start(self):
        page = self.get_page(self.base_url)

        file_content = self.extract_source_file(page)
        print(file_content)
        self.write_file("sourcecode.txt", file_content, 'w')

        url = 'https://apache.googlesource.com' + \
              page.find('div', {'class', 'u-sha1 u-monospace BlobSha1'}).findAll('a')[1]['href']
        source_code = self.code_to_list(file_content)

        map_relation = {}
        histories = self.scan_history(url, self.file_name)
        for history in histories:
            msg = history[0]
            diffs = history[1]

            formers = []
            latters = []
            for i in range(0, len(diffs)):
                diff = self.diff_convert(diffs[i])
                formers.append((diff[0], diff[1]))
                latters.append((diff[2], diff[3]))

            for i in range(len(latters) - 1, -1, -1):
                latter = latters[i][1]
                start_position = latters[i][0] - 1
                for j in range(len(latter) - 1, -1, -1):
                    if latter[j][1] == 1:
                        if source_code[j + start_position][1] >= 0:
                            map_relation[source_code[j + start_position][1]] = msg
                        del (source_code[start_position + j])

            for i in range(0, len(formers)):
                former = formers[i][1]
                start_position = formers[i][0] - 1
                for j in range(0, len(former)):
                    if former[j][1] == -1:
                        source_code.insert(start_position + j, (former[j][0], -1))
        return map_relation


crawler = Crawler('https://apache.googlesource.com/lucene-solr/+/ece75c9762ebde3ae62ad30b6e56cd4402ca7daf/src/java/org/apache/solr/core/CoreContainer.java', 'src/java/org/apache/solr/core/CoreContainer.java', 'diffs')
result = crawler.start()
#result = start('https://apache.googlesource.com/lucene-solr/+/ece75c9762ebde3ae62ad30b6e56cd4402ca7daf/src/java/org/apache/solr/core/CoreContainer.java', 'src/java/org/apache/solr/core/CoreContainer.java')

for item in list(result.items()):
    print(str(item[0] + 1) + ":" + str( item[1]))
print(result)




