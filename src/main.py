from urllib import request
from pathlib import Path
from zipfile import ZipFile
import sys, os
from seleniummm import WebDriver
import time
import traceback
import json
from subprocess import *

_print = print
print = lambda v, i=0: _print(i*'   ' + v, flush=True)

def execute_shell(args):
    print(f'shell command: ' + " ".join(args), 1)
    process = Popen(list(args), stdout=PIPE, stderr=PIPE)
    ret = []
    while process.poll() is None:
        line = process.stdout.readline()
        if isinstance(line, bytes):
            line = str(line, 'utf-8')
        if line != '' and line.endswith('\n'):
            ret.append(line[:-1])
    stdout, stderr = process.communicate()
    if isinstance(stdout, bytes):
        stdout = str(stdout, 'utf-8')
    if isinstance(stderr, bytes):
        stderr = str(stderr, 'utf-8')
    ret += stdout.split('\n')
    if stderr != '':
        ret += stderr.split('\n')
    ret.remove('')
    return ret

def setup_java():   # currently zulu 17 is required.
    java_path = (Path(root_path)/'java')
    java_path.mkdir(0o754, True, True)

    url = "https://cdn.azul.com/zulu/bin/zulu17.42.19-ca-jre17.0.7-macosx_x64.zip"
    file_name = Path(url[url.rfind('/', 0)+1:len(url)])
    java_version = str(file_name)[4:str(file_name).find('.', 0)]
    java_home = (java_path/file_name.stem/f'zulu-{java_version}.jre'/'Contents'/'Home'/'bin').absolute()

    # os.environ['JAVA_HOME'] = str(java_home)
    # os.environ['JAVA_PATH'] = str(java_home/'java')
    # print(f'JAVA_HOME: {os.environ["JAVA_HOME"]}')
    # print(f'JAVA_PATH: {os.environ["JAVA_PATH"]}')
    # os.environ['PATH'] = f"{os.environ['JAVA_HOME']}:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    # print(f"PATH: {os.environ['PATH']}")

    if java_home.exists():
        print(f'java is installed: {java_home}')
        result = execute_shell(['chmod', '755', '-R', str(java_home.parent)])
        print("\n".join(result), 1)
        return str(java_home)

    print(f'zip file downloading...', 1)
    response = request.urlretrieve(url, str(java_path/file_name))
    print(f'downloaded', 1)

    with ZipFile(str(java_path/file_name)) as f:
        f.extractall(str(java_path))

    result = execute_shell(['chmod', '755', '-R', str(java_home.parent)])
    print("\n".join(result), 1)
    
    return str(java_home)

def download_apks(version=None):
    def close_ad():
        try:
            # find full screen ad
            print('checking full screen ad...', 1)
            time.sleep(3)
            
            ad_ins = browser.find_elements(css='ins.adsbygoogle.adsbygoogle-noablate')
            for ins in ad_ins:
                inline_css = ins.get_attribute('style').replace(' ', '')
                if 'width:100vw' in inline_css and 'height:100vh' in inline_css:
                    outer_frame = browser.find_element(ins, tag='iframe')
                    browser.switch_to_frame(frame=outer_frame)
                    adframe = browser.find_element(id='ad_iframe')
                    browser.switch_to_frame(frame=adframe)
                    close_btn = browser.wait_until_element_visible(id='dismiss-button')
                    browser.click(close_btn)
                    browser.switch_to_frame(idx=0)
                    print('ad closed', 2)
        except:
            # no ad popup
            print('no ad', 2)
            pass

        # close popup ad
        while len(browser.driver.window_handles) > 1:
            browser.switch_to_window(1)
            browser.close()
            browser.switch_to_window(0)
            print('popup ad closed', 2)
            time.sleep(1)

    result = [ None, None ]
    try:
        browser = WebDriver(set_download_path=root_path+'/input')
        browser.get('https://www.apkmirror.com/apk/google-inc/youtube/')
        print('youtube page open')
        
        print('spread table content (see more uploads)', 1)
        browser.page_down()
        btn = browser.wait_until_element_clickable(css='div.table-row div.table-cell.center a') # first one is "see more uploads"
        browser.click(btn)
        close_ad()

        # find downloadable items in table. there may one or more variants. (bundle and apk)
        print('find item', 1)
        def go_target_apk_page(retry=0):
            if retry == 3:
                return False
            
            try:
                links = browser.wait_until_elements_visible(css='div.listWidget div div.appRow h5 a')
            except:     # if failed, check ad and try again
                print('something wrong...', 2)
                close_ad()
                return go_target_apk_page(retry+1)
            
            for link in links:
                if version == None or version in link.text:
                    print(f'apk webpage is found: {link.text} - {link.get_attribute("href")}', 2)
                    browser.click(link)
                    return True
                else:
                    continue
            return False

        if not go_target_apk_page():
            print('apk webpage is not found.')
            return tuple(result)
        
        def go_item_page(retry=0):
            if retry == 3:
                return False, None
            
            try:
                rows = browser.wait_until_elements_visible(css='div.table-row.headerFont')
            except:
                print('something wrong...', 2)
                close_ad()
                return go_item_page(retry+1)
            
            for row in rows:
                badges = browser.find_elements(row, css='span.apkm-badge')
                for badge in badges:
                    if badge.text == 'APK':
                        link = browser.find_element(row, css='a.accent_color')
                        ver = link.text
                        print(f'apk item page is found: {ver} - {link.get_attribute("href")}', 2)
                        browser.click(link)
                        return True, ver
            return False, None
        
        item_page_found, item_version = go_item_page()
        if not item_page_found:
            print('apk item page is not found.')
            return tuple(result)
        if version == None:     # set the version code as the downloading version
            version = item_version
        
        def get_download_page_link(retry=0) -> str:
            if retry == 3:
                return None
            
            try:
                down_btn = browser.wait_until_element_clickable(xpath="//a[@rel='nofollow' and contains(@class, 'downloadButton')]")
                url = down_btn.get_attribute('href')
                print('apk download page url is found: ' + url)
                return url
            except:
                print('something wrong...', 2)
                close_ad()
                return get_download_page_link(retry+1)

        if (download_page_url:=get_download_page_link()) == None:
            print('apk download page url is not found.')
            return tuple(result)
        
        cookies = browser.get_cookies()
    finally:
        browser.quit()

    def get_download_link(url, cookie):
        opener = request.build_opener()
        cookiestr = ""
        for c in cookie:
            cookiestr += f"{c['name']}={c['value']}; "
        opener.addheaders = [('cookie', cookiestr)]
        request.install_opener(opener)
        response = request.urlretrieve(url)
        with open(response[0], 'rt') as f:
            html = f.read()
            start = html.find('href="', html.find('<a rel="nofollow"'))+6
            end = html.find('">', start)
        os.remove(response[0])
        return "https://www.apkmirror.com" + html[start:end]
            # <a rel="nofollow" data-google-vignette="false" href="/wp-content/themes/APKMirror/download.php?id=4760949&amp;key=e3572129a0dcfdfa2cf5dad96076f869946c14ed&amp;forcebaseapk=true">here</a>

    print('prepare youtube apk...')
    download_folder = Path(root_path+'/input')
    try:
        apk_url = get_download_link(download_page_url, cookies)

        print('download from ' + apk_url, 1)
        apk_path = str((download_folder/f'youtube-{version}.apk').absolute())
        response = request.urlretrieve(apk_url, apk_path)
        request.install_opener(None)
        result[0] = apk_path
        print('youtube apk downloaded.', 1)
    except:
        print(traceback.format_exc())
        print('youtube apk downloading failed.', 1)

    print('prepare youtube music apk...')
    result[1] = ""
    print('youtube music apk downloaded.', 1)

    return tuple(result)

def download_revanced_cli():
    print('download lastest revanced cli')
    url = "https://api.github.com/repos/revanced/revanced-cli/releases/latest"
    response = request.urlopen(url)
    jdata = json.loads(response.read())
    name = jdata['assets'][0]['name']
    print('name: ' + name, 1)
    url = jdata['assets'][0]['browser_download_url']
    print('url: ' + url, 1)

    download_path = Path(root_path+'/input')/name
    if download_path.exists():
        print('latest revanced cli is in input folder', 2)
    else:
        response = request.urlretrieve(url, str(download_path.absolute()))
    
    return name, download_path

def download_revanced_patch():
    print('download lastest revanced patch')
    url = "https://api.github.com/repos/revanced/revanced-patches/releases/latest"
    response = request.urlopen(url)
    jdata = json.loads(response.read())
    for asset in jdata['assets']:
        name = asset['name']
        print('name: ' + name, 1)
        url = asset['browser_download_url']
        print('url: ' + url, 1)

        download_path = Path(root_path+'/input')/name
        if 'jar' in name and download_path.exists():
            print('latest revanced patch is in input folder', 2)
        else:   # always download patches.json 
            response = request.urlretrieve(url, str(download_path.absolute()))

    # find compatible youtube version
    md = jdata['body']
    try:
        start = md.find('`', md.find('support version', md.find('youtube')))+1
        end = md.find('`', start)
        youtube_version = md[start:end]
    except:
        youtube_version = None

    print('compatible youtube version: ' + youtube_version, 1)
    return name, download_path, youtube_version

def download_revanced_integrations():
    print('download lastest revanced integrations')
    url = "https://api.github.com/repos/revanced/revanced-integrations/releases/latest"
    response = request.urlopen(url)
    jdata = json.loads(response.read())
    asset = jdata['assets'][0]
    name = asset['name']
    print('name: ' + name, 1)
    url = asset['browser_download_url']
    print('url: ' + url, 1)

    download_path = Path(root_path+'/input')/name
    if 'jar' in name and download_path.exists():
        print('latest revanced patch is in input folder', 2)
    else:   # always download patches.json 
        response = request.urlretrieve(url, str(download_path.absolute()))
        
    return name, download_path

def patch_youtube(java_home, rv_path, patch_path, apk_path, integration_path, version):
    out_path = Path(root_path)/'output'
    out_path.mkdir(0o754, True, True)
    out_path = str(out_path/Path(apk_path).stem) + '.rv.apk'

    def find_applicable_patches(pkg_name, ver):
        patch_file = Path('input/patches.json')
        if not patch_file.exists():
            return None
        
        applicable_list = []
        exclude_list = [
            'enable-debugging'
        ]
        with patch_file.open('rt') as f:
            patch_list = json.load(f)
        for patch in patch_list:
            for pkg in patch['compatiblePackages']:
                if pkg_name == pkg['name'] and pkg_name not in exclude_list and (len(pkg['versions']) == 0 or version in pkg['versions']):
                    applicable_list.append(patch['name'])
        return applicable_list

    patches = find_applicable_patches('com.google.android.youtube', version)
    print('patches to be applied:\n' + '\n'.join(patches), 2)

    for b in range (0,len(patches)):
        patches.insert(b*2, '-i')

    java_path = java_home+'/java' if java_home != None else 'java'
    args = [java_path, '-jar', str(rv_path), '-a', apk_path, '-o', out_path, '-b', str(patch_path), '-m', str(integration_path), '--exclusive'] + patches
    result = execute_shell(args)
    print('\n'.join(result))
    return

def download_microg():
    print('download lastest microg apk')
    url = "https://api.github.com/repos/TeamVanced/VancedMicroG/releases/latest"
    response = request.urlopen(url)
    jdata = json.loads(response.read())
    asset = jdata['assets'][0]
    ver = jdata['tag_name']
    name = asset['name']
    print('name: ' + name, 1)
    url = asset['browser_download_url']
    print('url: ' + url, 1)

    download_path = Path(root_path+'/output')/f'{Path(name).stem}.{ver}.apk'
    if 'jar' in name and download_path.exists():
        print('latest microg apk is in output folder', 2)
    else:   # always download patches.json 
        response = request.urlretrieve(url, str(download_path.absolute()))
        
    return name, download_path


if __name__ == '__main__':
    global root_path
    if getattr(sys, 'frozen', False):
        root_path = str(Path(sys.executable).parent)
    else:
        root_path = './'

    # prepare download folder
    download_folder = Path(root_path+'/input')
    download_folder.mkdir(0o754, True, True)

    output_folder = Path(root_path+'/output')
    output_folder.mkdir(0o754, True, True)

    java_home = setup_java()
    rv_name, rv_path = download_revanced_cli()
    patch_name, patch_path, youtube_version = download_revanced_patch()
    integration_name, integration_path = download_revanced_integrations()
    microg_fname, migrog_path = download_microg()

    input_apk_path = (download_folder/f'youtube-{youtube_version}.apk')
    if not input_apk_path.exists():
        result = download_apks(youtube_version)
    else:
        result = (str(input_apk_path), None)

    if result[0]:   # pure youtube apk path
        patch_youtube(java_home, rv_path, patch_path, result[0], integration_path, youtube_version)

    