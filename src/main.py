import multiprocessing
multiprocessing.freeze_support()
from urllib import request
from pathlib import Path
from zipfile import ZipFile
import sys, os
from seleniummm import WebDriver
import time
import traceback
import json
from subprocess import *
import html
import argparse
from discord_webhook import DiscordWebhook as Discord
import shutil
import platform


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
    java_path = (Path(root_path)/'rv'/'java')
    java_path.mkdir(0o754, True, True)

    os_name = platform.system().casefold()
    if os_name == 'linux':
        url = 'https://cdn.azul.com/zulu/bin/zulu17.44.15-ca-jdk17.0.8-linux_x64.zip'
        file_name = Path(url[url.rfind('/', 0)+1:len(url)])
        java_home = (java_path/file_name.stem/'bin').absolute()
    elif os_name == 'darwin':
        url = "https://cdn.azul.com/zulu/bin/zulu17.44.15-ca-jre17.0.8-macosx_x64.zip"
        file_name = Path(url[url.rfind('/', 0)+1:len(url)])
        java_home = (java_path/file_name.stem/f'zulu-{java_version}.jre'/'Contents'/'Home'/'bin').absolute()
    else:   # windows
        url = "https://cdn.azul.com/zulu/bin/zulu17.44.15-ca-jdk17.0.8-win_x64.zip"
        file_name = Path(url[url.rfind('/', 0)+1:len(url)])
        java_home = (java_path/file_name.stem/'bin').absolute()
    java_version = str(file_name)[4:str(file_name).find('.', 0)]

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

def download_youtube(input_folder, version=None):
    input_apk_path = (input_folder/f'youtube-{version}.apk')
    if input_apk_path.exists():
        return str(input_apk_path), False
    
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

    try:
        browser = WebDriver(
            set_download_path=root_path+'/rv/input'
            #, visible=True
        )

        def go_target_apk_page(page=1, retry=0):
            if retry == 3:
                return False
            
            for i in range(page, 4):    # check 1~3 page
                browser.get(f'https://www.apkmirror.com/uploads/page/{i}/?appcategory=youtube')
                time.sleep(5)
                print('youtube page open: ' + str(i))
                try:
                    links = browser.wait_until_elements_visible(css='div.listWidget div div.appRow h5 a')
                except:     # if failed, check ad and try again
                    print('something wrong...', 2)
                    close_ad()
                    return go_target_apk_page(page=i, retry=retry+1)
                
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
            return None, False
        
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
            return None, False
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
            return None, False
        
        browser.get(download_page_url)
        
        cookies = browser.get_cookies()

        def get_download_link(url, cookie):
            opener = request.build_opener()
            cookiestr = ""
            for c in cookie:
                cookiestr += f"{c['name']}={c['value']}; "
            opener.addheaders = [('cookie', cookiestr)]
            request.install_opener(opener)
            response = request.urlretrieve(url)
            with open(response[0], 'rt') as f:
                htmlstr = f.read()
                start = htmlstr.find('href="', htmlstr.find('<a rel="nofollow"'))+6
                end = htmlstr.find('">', start)
            os.remove(response[0])
            return "https://www.apkmirror.com" + html.unescape(htmlstr[start:end]), opener
                # <a rel="nofollow" data-google-vignette="false" href="/wp-content/themes/APKMirror/download.php?id=4760949&amp;key=e3572129a0dcfdfa2cf5dad96076f869946c14ed&amp;forcebaseapk=true">here</a>

        print('prepare youtube apk...')
        download_folder = Path(root_path+'/rv/input')
        try:
            apk_url, opener = get_download_link(download_page_url, cookies)

            print('download from ' + apk_url, 1)
            apk_path = str((download_folder/f'youtube-{version}.apk').absolute())
            response = request.urlretrieve(apk_url, apk_path)
            request.install_opener(None)
            print('youtube apk downloaded.', 1)
        except:
            print(traceback.format_exc())
            print('youtube apk downloading failed.', 1)

        return apk_path, True
    finally:
        browser.quit()

def download_revanced_cli():
    print('download lastest revanced cli')
    url = "https://api.github.com/repos/revanced/revanced-cli/releases/latest"
    response = request.urlopen(url)
    jdata = json.loads(response.read())
    name = jdata['assets'][0]['name']
    print('name: ' + name, 1)
    url = jdata['assets'][0]['browser_download_url']
    print('url: ' + url, 1)

    download_path = Path(root_path+'/rv/input')/name
    if download_path.exists():
        is_new = False
        print('latest revanced cli is in input folder', 2)
    else:
        response = request.urlretrieve(url, str(download_path.absolute()))
        is_new = True
    
    return name, download_path, is_new

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

        download_path = Path(root_path+'/rv/input')/name
        if 'jar' in name and download_path.exists():
            print('latest revanced patch is in input folder', 2)
            is_new = False
        else:   # always download patches.json 
            response = request.urlretrieve(url, str(download_path.absolute()))
            is_new = True

    # find compatible youtube version
    # use first encountered youtube version
    youtube_version = None
    with (Path(root_path + '/rv/input/patches.json')).open('rt') as f:
        patches = json.load(f)
    for patch in patches:
        for pkg in patch['compatiblePackages']:
            versions = pkg['versions']
            if len(versions) > 0:
                youtube_version = versions[-1]
                break
        if youtube_version:
            break
    
    print('compatible youtube version: ' + youtube_version, 1)
    return name, download_path, youtube_version, is_new

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

    download_path = Path(root_path+'/rv/input')/name
    if 'apk' in name and download_path.exists():
        print('latest revanced patch is in input folder', 2)
        is_new = False
    else:   # always download patches.json 
        response = request.urlretrieve(url, str(download_path.absolute()))
        is_new = True
        
    return name, download_path, is_new

def get_new_youtube_path(opt_path, apk_stem):
    out_path = Path(root_path)/'rv'/'output/'
    out_path.mkdir(0o754, True, True)

    if opt_path:
        with open(opt_path) as f:
            opts = json.load(f)
        for opt in opts:
            if opt['patchName'] == 'Custom branding':
                keyword = opt['options'][0]['value']
                if keyword:
                    tail = ('.' + keyword)
                    break
    return str(out_path/(apk_stem + tail + '.rv.apk'))

def patch_youtube(java_home, cli_path, patch_path, apk_path, integration_path, version, args):
    out_path = get_new_youtube_path(args.opt_path, Path(apk_path).stem)

    def find_applicable_patches(pkg_name, ver):
        patch_file = Path(root_path + '/rv/input/patches.json')
        if not patch_file.exists():
            return None
        
        applicable_list = []
        exclude_list = [
            'enable-debugging'
            'custom-'
        ]
        with patch_file.open('rt') as f:
            patch_list = json.load(f)
        patch_name_format = '"{}"' if args.dry_run else '{}'
        for patch in patch_list:
            patch_name = patch['name'].lower().replace(' ', '-')    # conversion according to naming convension
            if len(patch['compatiblePackages']) == 0 and patch['excluded'] != True:   # universal patches which are not
                applicable_list.append(patch_name_format.format(patch_name))
            for pkg in patch['compatiblePackages']:
                if pkg_name == pkg['name'] and pkg_name not in exclude_list and (len(pkg['versions']) == 0 or version in pkg['versions']):
                    applicable_list.append(patch_name_format.format(patch_name))
        return applicable_list

    patches = find_applicable_patches('com.google.android.youtube', version)
    print('patches to be applied:\n         ' + '\n         '.join(patches), 2)

    for b in range (0,len(patches)):
        patches.insert(b*2, '-i')

    def find_keystore():
        dir = (Path(root_path + '/rv/output'))
        if dir.exists():
            for file in dir.iterdir():
                if file.is_file() and file.suffix == '.keystore':
                    return str(file.absolute())
        return None

    java_path = java_home+'/java' if java_home != None else 'java'
    cmd = [java_path, '-jar', str(cli_path), 'patch', '--exclusive', '-o', out_path, '-b', str(patch_path), '-m', str(integration_path)]
    if (keystore := find_keystore()):
        cmd += ['--keystore='+keystore ]
    cmd += patches
    if args.opt_path:
        cmd += ['-i', 'change-package-name']
        cmd += [f'--options={args.opt_path}']
    cmd += [apk_path]
    if not args.dry_run:
        result = execute_shell(cmd)
        print('\n'.join(result))

        print('purge caches')
        cmd = ['rm', '-rf', 'revanced-cache', 'revanced-resource-cache']
        result = execute_shell(cmd)
        print('\n'.join(result))
    return out_path

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

    download_path = Path(root_path+'/rv/output')/f'{Path(name).stem}.{ver}.apk'
    if 'apk' in name and download_path.exists():
        print('latest microg apk is in output folder', 2)
        is_new = False
    else:   # always download patches.json 
        response = request.urlretrieve(url, str(download_path.absolute()))
        is_new = True
        
    return name, download_path, is_new

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--options', type=str, help='options file path', default=None, action='store', dest='opt_path')
    parser.add_argument('--out_path', type=str, help='path to write patched apk file', default=None, action='store', dest='out_path')
    parser.add_argument('--download_link', type=str, help='base url of download link for patched apk file', default=None, action='store', dest='down_link')
    parser.add_argument('--notice', help='notice discord the result if new apk is ready', default=False, action='store_true', dest='notice')
    parser.add_argument('--dry-run', help='show the command', default=False, action='store_true', dest='dry_run')
    args = parser.parse_args()
    
    global root_path
    if getattr(sys, 'frozen', False):
        root_path = str((Path(sys.executable).parent))
    else:
        root_path = './'

    # prepare download folder
    download_folder = Path(root_path+'/rv/input')
    download_folder.mkdir(0o754, True, True)

    output_folder = Path(root_path+'/rv/output')
    output_folder.mkdir(0o754, True, True)

    java_home = setup_java()
    need_update = False
    cli_name, cli_path, is_new = download_revanced_cli()
    need_update = need_update or is_new

    patch_name, patch_path, youtube_version, is_new = download_revanced_patch()
    need_update = need_update or is_new

    integration_name, integration_path, is_new = download_revanced_integrations()
    need_update = need_update or is_new

    microg_fname, migrog_path, is_new = download_microg()
    need_update = need_update or is_new

    youtube_apk_path, is_new = download_youtube(download_folder, youtube_version)
    need_update = need_update or is_new

    new_apk_path = get_new_youtube_path(args.opt_path, Path(youtube_apk_path).stem)
    need_update = need_update or not Path(new_apk_path).exists()

    if not need_update:
        print('nothing new...')
    elif not youtube_apk_path:   # pure youtube apk path
        print('youtube apk file not found...')
    else :  
        new_apk_path = patch_youtube(java_home, cli_path, patch_path, youtube_apk_path, integration_path, youtube_version, args)

        if args.out_path:
            dest_path = args.out_path + '/' + Path(new_apk_path).name
            print('move to outpath -> ' + args.out_path)
            shutil.copy(new_apk_path, dest_path)

        print('send result to discord')
        if new_apk_path and args.notice:
            with open('./secret/rvhelper', 'rt') as f:
                url = f.readline().strip()
            
            discord = Discord(url)
            filename = str(Path(new_apk_path).name)
            msg = f'{filename} is ready!'
            if args.down_link:
                msg += f'{os.linesep}{args.down_link}{filename}'
            discord.set_content(msg)
            resp = discord.execute()
            print(f'resp: {resp.status_code}: {resp.reason}')
        print('all done')

    