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
from subprocess import run, PIPE
import html
import argparse
from discord_webhook import DiscordWebhook as Discord
import shutil
import platform
from urllib.error import HTTPError
from enum import Enum

_print = print
print = lambda v, i=0: _print(i*'   ' + v, flush=True)

class PKG_NAME(str, Enum):
    TUBE = 'com.google.android.youtube'

    @classmethod
    def __repr__(self):
        return self.value()
    
class PROVIDER(dict, Enum):
    """{'path':path, 'name':name}"""
    OFFICIAL={'path':"revanced",
              'name':"official"}
    EXTENDED={'path':"inotia00",
              'name':"extended"}
    
def execute_shell(args):
    print(f'shell command: ' + " ".join(args), 1)
    result = run(args, stdout=PIPE, stderr=PIPE)
        
    ret = []
    ret.extend(result.stdout.decode().split('\n'))
    ret.extend(result.stderr.decode().split('\n'))

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
        java_version = str(file_name)[4:str(file_name).find('.', 0)]
        java_home = (java_path/file_name.stem/f'zulu-{java_version}.jre'/'Contents'/'Home'/'bin').absolute()
    else:   # windows
        url = "https://cdn.azul.com/zulu/bin/zulu17.44.15-ca-jdk17.0.8-win_x64.zip"
        file_name = Path(url[url.rfind('/', 0)+1:len(url)])
        java_home = (java_path/file_name.stem/'bin').absolute()
    
    # os.environ['JAVA_HOME'] = str(java_home)
    # os.environ['JAVA_PATH'] = str(java_home/'java')
    # print(f'JAVA_HOME: {os.environ["JAVA_HOME"]}')
    # print(f'JAVA_PATH: {os.environ["JAVA_PATH"]}')
    # os.environ['PATH'] = f"{os.environ['JAVA_HOME']}:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    # print(f"PATH: {os.environ['PATH']}")

    if java_home.exists():
        print(f'java is installed: {java_home}')
    else:
        print(f'zip file downloading...', 1)
        response = request.urlretrieve(url, str(java_path/file_name))
        print(f'downloaded', 1)

        with ZipFile(str(java_path/file_name)) as f:
            f.extractall(str(java_path))

    result = execute_shell(['chmod', '-R', '755', str(java_home.parent)])
    print("\n".join(result), 1)
    
    return str(java_home)

def download_youtube(input_folder, version=None):
    def close_ad():
        try:
            # find full screen ad
            print('checking full screen ad...', 1)
            time.sleep(2)

            iframe = browser.find_element(xpath="//ins/div[contains(@id, 'google_ads_iframe')]/iframe")
            browser.switch_to_frame(iframe)
            try:
                browser.click(id='dismiss-button')  # try close button in outside of ad_iframe
            except:
                browser.switch_to_frame(frame=browser.find_element(id='ad_iframe'))
                browser.click(id='dismiss-button')
            browser.switch_to_frame()
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

    def go_target_apk_page(page=1, retry=0):
        if retry == 3:
            return False
        
        for i in range(page, 4):    # check 1~3 page
            browser.get(f'https://www.apkmirror.com/uploads/page/{i}/?appcategory=youtube')
            time.sleep(2)
            print('youtube page open: ' + str(i))
            try:
                links = browser.wait_until_elements_presence(css='div.listWidget div div.appRow h5 a')
            except:     # if failed, check ad and try again
                print('something wrong...', 2)
                close_ad()
                return go_target_apk_page(page=i, retry=retry+1)
            
            for link in links:
                if version == None or version in link.text:
                    print(f'apk webpage is found: {link.text} - {link.get_attribute("href")}', 2)
                    browser.get(link.get_attribute("href"))
                    return True
                else:
                    continue
        return False

    def go_item_page(retry=0):
        if retry == 3:
            return False, None
        
        try:
            rows = browser.wait_until_elements_presence(css='div.table-row.headerFont')
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
                    browser.get(link.get_attribute("href"))
                    return True, ver
        return False, None
        
    def get_download_page_link(retry=0) -> str:
        if retry == 3:
            return None
        
        try:
            down_btn = browser.wait_until_elements_presence(xpath="//a[@rel='nofollow' and contains(@class, 'downloadButton')]")[0]
            url = down_btn.get_attribute('href')
            print('apk download page url is found: ' + url, 2)
            return url
        except:
            print('something wrong...', 2)
            close_ad()
            return get_download_page_link(retry+1)

    def get_download_link(url):
        cookies = browser.get_cookies()
        opener = request.build_opener()
        cookiestr = ""
        for c in cookies:
            cookiestr += f"{c['name']}={c['value']}; "
        opener.addheaders = [('cookie', cookiestr)]
        request.install_opener(opener)
        response = request.urlretrieve(url)
        with open(response[0], 'rt') as f:
            htmlstr = f.read()
            start = htmlstr.find('href="', htmlstr.find(' rel="nofollow"'))+6
            end = htmlstr.find('">', start)
        os.remove(response[0])
        return "https://www.apkmirror.com" + html.unescape(htmlstr[start:end])
            # <a rel="nofollow" data-google-vignette="false" href="/wp-content/themes/APKMirror/download.php?id=4760949&amp;key=e3572129a0dcfdfa2cf5dad96076f869946c14ed&amp;forcebaseapk=true">here</a>

    input_apk_path = (input_folder/f'youtube-{version}.apk')
    if input_apk_path.exists():
        return str(input_apk_path), False
    
    print('visit apkmirror')
    browser = WebDriver(
        set_download_path=root_path+'/rv/input'
        , disable_download=True
        # , debug_port=random.randrange(19000, 19299)
        , user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
        , debug_port=19208
        , use_stealth=True
        # , driver_preference='standard'
        # , visible=True
    )

    try:
        # try directly access to corresponding version page
        browser.get(f'https://www.apkmirror.com/apk/google-inc/youtube/youtube-{version}-release/')
        try:
            browser.wait_until_element_visible(css='div.errorPage') # if error, find page from list
            if not go_target_apk_page():
                print('apk webpage is not found.', 1)
                return None, False
        except:
            pass        # direct access succeeded.
        
        item_page_found, item_version = go_item_page()
        if not item_page_found:
            print('apk item page is not found.', 1)
            return None, False
        if version == None:     # set the version code as the downloading version
            version = item_version

        if (download_page_url:=get_download_page_link()) == None:
            print('apk download page url is not found.', 1)
            return None, False
        
        browser.get(download_page_url)
        print('prepare youtube apk...')
        download_folder = Path(root_path+'/rv/input')
        try:
            apk_url = get_download_link(download_page_url)
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

def download_revanced_cli(provider:PROVIDER):
    print('download lastest revanced cli')
    url = f"https://api.github.com/repos/{provider['path']}/revanced-cli/releases/latest"
    # opener = request.build_opener()
    response = request.urlopen(url)
    jdata = json.loads(response.read())

    name = Path(jdata['assets'][0]['name'])
    name = f"{name.stem}.{provider['name']}{name.suffix}"
    ver = jdata['tag_name']
    print('name: ' + name, 1)
    url = jdata['assets'][0]['browser_download_url']
    print('url: ' + url, 1)

    download_path = Path(root_path+'/rv/input')/name
    if download_path.exists():
        is_new = False
        print('latest revanced cli is in input folder', 2)
    else:
        try:
            response = request.urlretrieve(url, str(download_path.absolute()))
            is_new = True
        except HTTPError as e:
            print('failed to get revanced cli from github. skipped', 2)
            is_new = False
    
    return download_path, is_new, f'c{ver[1:]}'

def download_revanced_patch(pkg_name, provider:PROVIDER):
    print('download lastest revanced patch')
    url = f"https://api.github.com/repos/{provider['path']}/revanced-patches/releases/latest"
    response = request.urlopen(url)
    jdata = json.loads(response.read())
    ver = jdata['tag_name']
    lib_name = None
    list_name = None
    scheme_v5 = False

    download_path = Path(root_path+'/rv/input')
    for asset in jdata['assets']:
        name = Path(asset['name'])
        if name.suffix == '.jar':
            name = f"{name.stem}.{provider['name']}{name.suffix}"
            lib_name = name
            fpath = download_path/name
        elif name.suffix == '.json':
            name = f"{name.stem}.{provider['name']}.{ver}{name.suffix}"
            list_name = name
            fpath = download_path/name
        elif name.suffix == '.rvp' or name.suffix == '.asc':
            name = f"{name.stem}.{provider['name']}{name.suffix}"
            if Path(name).suffix == '.rvp':
                lib_name = name
            fpath = download_path/name
            scheme_v5 = True

        url = asset['browser_download_url']
        print(f'{name}: {url}', 1)

        if fpath.exists():
            print(f'latest {name} file is in input folder', 2)
            is_new = False and is_new
        else:
            try :
                response = request.urlretrieve(url, str(fpath.absolute()))
                is_new = True
            except HTTPError as e:
                print('failed to get {name} from github. skipped', 2)
                is_new = False and is_new
    
    if scheme_v5:
        return download_path/lib_name, None, None, is_new, f'p{ver[1:]}'

    # find compatible youtube version
    # use the highest version
    youtube_versions = []
    with (Path(root_path + '/rv/input/' + list_name)).open('rt') as f:
        patches = json.load(f)
    for patch in patches:
        if not patch['compatiblePackages']: # universal patch
            continue 

        for pkg in patch['compatiblePackages']:
            if pkg['name'] != pkg_name:
                continue
            versions = pkg['versions']
            if versions != None and len(versions) > 0:
                youtube_versions.extend(versions)
                break
    
    youtube_versions = sorted(set(youtube_versions))
    
    print('compatible youtube version: ' + youtube_versions[-1], 1)
    return download_path/lib_name, download_path/list_name, youtube_versions[-1], is_new, f'p{ver[1:]}'

def download_revanced_integrations(provider:PROVIDER):
    print('download lastest revanced integrations')
    url = f"https://api.github.com/repos/{provider['path']}/revanced-integrations/releases/latest"
    response = request.urlopen(url)
    jdata = json.loads(response.read())
    asset = jdata['assets'][0]
    name = Path(asset['name'])
    ver = jdata['tag_name']
    name = f"{name.stem}.{provider['name']}{name.suffix}"
    url = asset['browser_download_url']
    print(f'{name}: {url}', 1)

    download_path = Path(root_path+'/rv/input')/name
    if 'apk' in name and download_path.exists():
        print('latest revanced patch is in input folder', 2)
        is_new = False
    else:
        try:
            response = request.urlretrieve(url, str(download_path.absolute()))
            is_new = True
        except Exception as e:
            pass

    return download_path, is_new, f'i{ver[1:]}'

def _get_custom_branding(args):
    if args.options_path:
        with open(args.options_path) as f:
            opts = json.load(f)
        for opt in opts:
            if opt['patchName'] == 'Custom branding' or opt['patchName'] == 'Custom branding name YouTube':
                keyword = opt['options'][0]['value']
                if keyword:
                    return keyword
    return None

def _get_custom_package_name(args):
    if args.options_path:
        with open(args.options_path) as f:
            opts = json.load(f)
        for opt in opts:
            if opt['patchName'] == 'Change package name':
                keyword = opt['options'][0]['value']
                if keyword:
                    return keyword
    return None


def get_new_youtube_path(args, apk_stem, provider:PROVIDER, apply_versions):
    out_path = Path(args.out_path)
    out_path.mkdir(0o754, True, True)

    branding = _get_custom_branding(args)
    if branding:
        branding = f'-{branding.replace(" ", "_")}-'
    else:
        branding = ''

    return str(out_path/(f"{apk_stem}-{'-'.join(apply_versions)}{branding}{provider.name}.apk"))

def _find_keystore():
    dir = (Path(root_path + '/rv/output'))
    if dir.exists():
        for file in dir.iterdir():
            if file.is_file() and file.suffix == '.keystore':
                return str(file.absolute())
    return None
    
def patch_youtube_v5(java_home, cli_path, patch_lib_path, apk_path, version, provider, apply_versions, args):
    out_path = get_new_youtube_path(args, Path(apk_path).stem, provider, apply_versions)
    java_path = java_home+'/java' if java_home != None else 'java'
    cmd = [java_path, '-jar', str(cli_path), 'patch', '-o', out_path, f'--patches={patch_lib_path}', '--keystore-entry-alias=alias', '--keystore-entry-password=ReVanced']
    if args.purge_cache:
        cmd.append('--purge')
    if (keystore := _find_keystore()):
        cmd.append('--keystore='+keystore)
    if (branding := _get_custom_branding(args)):
        cmd.extend(['--enable=Custom branding', f'-OappName={branding}'])
    if (pkgName := _get_custom_package_name(args)):
        cmd.extend(['--enable=Change package name', f'-OpackageName={pkgName}'])
    cmd.append(apk_path)

    if not args.dry_run:
        result = execute_shell(cmd)
        print('\n'.join(result))
    return out_path

def patch_youtube(java_home, cli_path, patch_lib_path, patch_list_path, apk_path, integration_path, version, provider, apply_versions, args):
    out_path = get_new_youtube_path(args, Path(apk_path).stem, provider, apply_versions)

    def find_applicable_patches(pkg_name, ver):
        if not patch_list_path.exists():
            return None
        
        applicable_list = []
        include_list = [
            'Change package name',
            'Export all activities'
        ]
        exclude_list = [
            'Enable debugging',
            # 'Export all activities',      # crashed
            'Enable Android debugging'
        ]
        with patch_list_path.open('rt') as f:
            patch_list = json.load(f)
        patch_name_format = '"{}"' if args.dry_run else '{}'
        print('patches to be excluded', 2)
        for patch in patch_list:
            patch_name = patch['name']
            if patch_name in exclude_list:
                print(f'-{patch_name}', 3)
                continue
            elif patch['compatiblePackages'] == None:   # universal patches which are default to use
                if patch['use'] == True or patch_name in include_list:
                    applicable_list.append(patch_name_format.format(patch_name))
                else:
                    print(f'-{patch_name}', 3)
                continue

            for pkg in patch['compatiblePackages']:
                if pkg_name == pkg['name']:
                    if pkg['versions'] == None or len(pkg['versions']) == 0 or version in pkg['versions']:
                        applicable_list.append(patch_name_format.format(patch_name))
                    else:
                        print(f'-{patch_name}', 3)
        return applicable_list

    patches = find_applicable_patches(PKG_NAME.TUBE, version)
    print('patches to be applied:\n         +' + '\n         +'.join(patches), 2)

    for b in range (0,len(patches)):
        patches.insert(b*2, '-i')

    java_path = java_home+'/java' if java_home != None else 'java'
    cmd = [java_path, '-jar', str(cli_path), 'patch', '--exclusive', '-o', out_path, '-b', str(patch_lib_path), '-m', str(integration_path), '--alias', 'alias', '--keystore-entry-password', 'ReVanced']
    if args.purge_cache:
        cmd += ['-p']
    if (keystore := _find_keystore()):
        cmd += ['--keystore='+keystore ]
    cmd += patches
    if args.options_path:
        print(f'update {args.options_path} if required')
        opt_cmd = [java_path, '-jar', str(cli_path), 'options', f'-p={args.options_path}', '-o', '-u', str(patch_lib_path)]
        result = execute_shell(opt_cmd)
        print('\n'.join(result))

        cmd += [f'--options={args.options_path}']
    cmd += [apk_path]
    if not args.dry_run:
        result = execute_shell(cmd)
        print('\n'.join(result))
    return out_path

def download_microg():
    print('download lastest microg apk')
    url = "https://api.github.com/repos/TeamVanced/VancedMicroG/releases/latest"
    response = request.urlopen(url)
    jdata = json.loads(response.read())
    asset = jdata['assets'][0]      # always in first item
    ver = jdata['tag_name']
    name = f'{Path(asset["name"]).stem}.{ver}.apk'
    url = asset['browser_download_url']
    print(f'{name}: {url}', 1)

    download_path = Path(root_path+'/rv/output')/name
    if download_path.exists():
        print('latest microg apk is in output folder', 2)
        is_new = False
    else:
        response = request.urlretrieve(url, str(download_path.absolute()))
        is_new = True
        
    return download_path, is_new

def send_msg(msg:str):
    global root_path
    with open(root_path+'/secret/rvhelper', 'rt') as f:
        discord_url = f.readline().strip()
    
    discord = Discord(discord_url)
    discord.set_content(msg)
    return discord.execute()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', help='batch file. ignore all other arguments.', default=None, action='store', type=str, dest='batch')
    parser.add_argument('--options', help='options file path', default=None, action='store', type=str, dest='options_path')
    parser.add_argument('--out_path', help='path to write patched apk file', default=None, action='store', type=str, dest='out_path')
    parser.add_argument('--download_link', help='base url of download link for patched apk file', default=None, type=str, action='store', dest='download_link')
    parser.add_argument('--notice', help='notice discord the result if new apk is ready', default=False, action='store_true', dest='notice')
    parser.add_argument('--extended', help='use revanced extended', default=False, action='store_true', dest='extended')
    parser.add_argument('--purge-cache', help='purge cache', default=True, action='store_false', dest='purge_cache')
    parser.add_argument('--dry-run', help='show the command', default=False, action='store_true', dest='dry_run')
    args = parser.parse_args()
    
    global root_path
    if getattr(sys, 'frozen', False):
        root_path = str((Path(sys.executable).parent))
    else:
        root_path = './'

    def exec_v4(provider:PROVIDER, download_folder, java_home, need_update, cli_path, is_new, cli_version):
        print('cli v4')

        patch_lib_path, patch_list_path, youtube_version, is_new, patch_version = download_revanced_patch(PKG_NAME.TUBE, provider)
        need_update = need_update or is_new

        integration_path, is_new, integ_version = download_revanced_integrations(provider)
        need_update = need_update or is_new

        youtube_apk_path, is_new = download_youtube(download_folder, youtube_version)
        need_update = need_update or is_new

        apply_versions = [cli_version, patch_version, integ_version]
        new_apk_path = get_new_youtube_path(args, Path(youtube_apk_path).stem, provider, apply_versions=apply_versions)
        print(f'check latest build in {new_apk_path}')
        if not Path(new_apk_path).exists():
            print(f'new apk not found. build required.', 1)
            need_update = True

        if not need_update:
            print('nothing new...')
        elif not youtube_apk_path:   # pure youtube apk path
            print('youtube apk file not found...')
            return new_apk_path, False
        else:
            new_apk_path = patch_youtube(java_home, 
                                        cli_path, 
                                        patch_lib_path,
                                        patch_list_path,
                                        youtube_apk_path, 
                                        integration_path, 
                                        youtube_version, 
                                        provider,
                                        apply_versions,
                                        args)
        return new_apk_path, need_update

    def exec_v5(provider:PROVIDER, download_folder, java_home, need_update, cli_path, is_new, cli_version):
        patch_lib_path, patch_list_path, youtube_version, is_new, patch_version = download_revanced_patch(PKG_NAME.TUBE, provider)
        need_update = need_update or is_new

        # FOR TEST
        # patch_lib_path = Path('rv/input/patches-5.0.0.official.rvp')
        # patch_version = 'p5.0.0'
        # is_new = True

        java_path = java_home+'/java' if java_home != None else 'java'
        # TODO parse option list
        # cmd = [java_path, '-jar', str(cli_path), 
        #        'list-patches', 
        #        '--with-options', 
        #        '--with-packages', 
        #        '--with-versions', 
        #        '-f=com.google.android.youtube', 
        #        str(patch_lib_path)]
        # result = execute_shell(cmd)
        
        cmd = [java_path, '-jar', str(cli_path), 
               'list-versions', 
               '-f=com.google.android.youtube', 
               str(patch_lib_path)]
        result = execute_shell(cmd)
        youtube_version = ''
        for line in result:
            tmpVer = line.strip().split(' ')[0]
            if tmpVer.split('.')[0].isnumeric() and youtube_version < tmpVer:
                youtube_version = tmpVer
        print(f'applicable youtube version : {youtube_version}')

        youtube_apk_path, is_new = download_youtube(download_folder, youtube_version)
        need_update = need_update or is_new

        apply_versions = [cli_version, patch_version]
        new_apk_path = get_new_youtube_path(args, Path(youtube_apk_path).stem, provider, apply_versions=apply_versions)
        print(f'check latest build in {new_apk_path}')
        if not Path(new_apk_path).exists():
            print(f'new apk not found. build required.', 1)
            need_update = True

        if not need_update:
            print('nothing new...')
        elif not youtube_apk_path:   # pure youtube apk path
            print('youtube apk file not found...')
            return new_apk_path, False
        else:
            new_apk_path = patch_youtube_v5(java_home, 
                                        cli_path, 
                                        patch_lib_path,
                                        youtube_apk_path, 
                                        youtube_version, 
                                        provider,
                                        apply_versions,
                                        args)
        return new_apk_path, need_update

        # Index: 
        # Name: 
        # Description: 
        # Enabled: 
        # Options: 

    def execute():
        try:
            if not args.out_path:
                args.out_path = f'{root_path}/rv/output/'
            if args.out_path and args.out_path[0] == '~':
                args.out_path = os.path.expanduser(args.out_path)
            print('='*50)
            print(f'options: {args.options_path}')
            print(f'output: {args.out_path}')
            print('='*50)

            if args.extended:
                provider = PROVIDER.EXTENDED
            else:
                provider = PROVIDER.OFFICIAL

            # prepare download folder
            download_folder = Path(root_path+'/rv/input')
            download_folder.mkdir(0o754, True, True)

            output_folder = Path(root_path+'/rv/output')
            output_folder.mkdir(0o754, True, True)

            java_home = setup_java()

            microg_path, is_new = download_microg()
            if is_new and microg_path and args.out_path:
                dest_path = args.out_path + '/' + Path(microg_path).name
                print('move new microg to ' + args.out_path)
                shutil.copy(microg_path, dest_path)

            need_update = False
            cli_path, is_new, cli_version = download_revanced_cli(provider)
            need_update = need_update or is_new

            # FOR TEST
            # need_update = False
            # microg_path = Path('rv/output/microg.v0.2.24.220220-220220001.apk')
            # cli_path = Path('rv/input/revanced-cli-5.0.0-all.official.jar')
            # cli_version = 'c5.0.0'
            # is_new = True

            if(cli_version.replace('c', '').startswith('4.')):
                new_apk_path, updated = exec_v4(provider, download_folder, java_home, need_update, cli_path, is_new, cli_version)
            else:
                new_apk_path, updated = exec_v5(provider, download_folder, java_home, need_update, cli_path, is_new, cli_version)

            # build succeeded
            if Path(new_apk_path).exists():
                print(f'new apk: {new_apk_path}')
                
                if args.notice and updated:
                    print('send result to discord')
                    filename = str(Path(new_apk_path).name)
                    msg = f'{filename} 준비!{os.linesep}'
                    if args.download_link:
                        msg += f'{args.download_link}{filename}{os.linesep}'
                        msg += f'(전체 목록: {args.download_link}){os.linesep}'
                    resp = send_msg(msg)
                    print(f'resp: {resp.status_code}: {resp.reason}')
            elif args.notice:
                resp = send_msg('failed to build new youtube...', 1)
                print(f'resp: {resp.status_code}: {resp.reason}')
                
            print('all done')
        except:
            print(traceback.format_exc())
            print('failed to complete rv_helper')
            resp = send_msg('failed to complete rv_helper')
            print(f'resp: {resp.status_code}: {resp.reason}')

    if args.batch:
        with open(args.batch, 'rt') as f:
            jobs = json.load(f)
        for job in jobs:
            for key in job.keys():
                args.__setattr__(key, job[key])
            execute()

    #https://colab.research.google.com/github/Jarvis-Ank/Re-Vanced/blob/main/Re-Vanced.ipynb