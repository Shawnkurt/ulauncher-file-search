""" Main Module """

import logging
import os
import subprocess
import mimetypes
import shutil
import gi
import re
gi.require_version('Gtk', '3.0')
# pylint: disable=import-error
from gi.repository import Gio, Gtk
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.item.ExtensionSmallResultItem import ExtensionSmallResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.OpenAction import OpenAction
from ulauncher.api.shared.action.RunScriptAction import RunScriptAction
from ulauncher.api.shared.action.DoNothingAction import DoNothingAction
from ulauncher.api.shared.action.HideWindowAction import HideWindowAction

logger = logging.getLogger(__name__)

FILE_SEARCH_ALL = 'ALL'
FILE_SEARCH_DIRECTORY = 'DIR'
FILE_SEARCH_FILE = 'FILE'


class FileSearchExtension(Extension):
    """ Main Extension Class  """

    def __init__(self):
        """ Initializes the extension """
        super(FileSearchExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())

    def search(self, query, file_type=None):
        """ Search files using fd/fdfind """

        # 优先使用 fd；如果没有，再尝试 fdfind
        if shutil.which('fd'):
            bin_name = 'fd'
        elif shutil.which('fdfind'):
            bin_name = 'fdfind'
        else:
            logger.error('Neither fd nor fdfind was found in PATH')
            return []

        cmd = [
            'timeout', '5s', 'ionice', '-c', '3', bin_name, '--threads', '1',
            #'--hidden'
        ]

        # 是否显示隐藏的文件或目录
        if self.preferences['show_hidden'] == 'true':
            cmd.append('--hidden')

        if file_type == FILE_SEARCH_FILE:
            cmd.append('-t')
            cmd.append('f')
        elif file_type == FILE_SEARCH_DIRECTORY:
            cmd.append('-t')
            cmd.append('d')

        # 多个基目录
        for path in self.preferences['base_dir'].split(';'):
            cmd.append('--search-path')
            cmd.append(path)

        # 多个关键词，就一层层筛选
        for index, kw in enumerate(query.split(' ')):
            if index != 0:
                cmd.append('| grep')
            cmd.append(kw)

        # 把生成的命令输出到日志
        logger.info(' '.join(cmd))

        # subprocess.run 如果命令是数组，就不能使用管道符。
        # 所以这里转成字符串并使用 shell=True
        process = subprocess.run(
            ' '.join(cmd),
            stdout=subprocess.PIPE,
            encoding='utf-8',
            shell=True
        )
        out = process.stdout
        if process.returncode != 0:
            logger.error(process.returncode)

        files = out.split('\n')
        files = [_f for _f in files if _f]  # remove empty lines

        result = []

        # get folder icon outside loop, so it only happens once
        file = Gio.File.new_for_path("/")
        folder_info = file.query_info('standard::icon', 0, Gio.Cancellable())
        folder_icon = folder_info.get_icon().get_names()[0]
        icon_theme = Gtk.IconTheme.get_default()
        icon_folder = icon_theme.lookup_icon(folder_icon, 128, 0)
        if icon_folder:
            folder_icon = icon_folder.get_filename()
        else:
            folder_icon = "images/folder.png"

        try:
            max_results = int(self.preferences.get('max_results', '15'))
        except (TypeError, ValueError):
            max_results = 15

        for f in files[:max_results]:
            if os.path.isdir(f):
                icon = folder_icon
            else:
                type_, encoding = mimetypes.guess_type(f)

                if type_:
                    file_icon = Gio.content_type_get_icon(type_)
                    file_info = icon_theme.choose_icon(file_icon.get_names(), 128, 0)
                    if file_info:
                        icon = file_info.get_filename()
                    else:
                        icon = "images/file.png"
                else:
                    icon = "images/file.png"

            result.append({'path': f, 'name': f, 'icon': icon})

        return result

    def get_open_in_file_manager_action(self, path):
        """ 用默认文件管理器打开所在位置 """
        target = path if os.path.isdir(path) else os.path.dirname(path)
        if not target:
            target = path
        return OpenAction(target)


class KeywordQueryEventListener(EventListener):
    """ Listener that handles the user input """

    # pylint: disable=unused-argument,no-self-use
    def on_event(self, event, extension):
        """ Handles the event """
        items = []

        query = event.get_argument()

        # 没有输入, 或输入只有1个英文字符，就不搜索
        if (query is None) or (re.match('^[a-zA-Z0-9]+', query) and len(query) == 1):
            logger.info('只有1个英文字符')
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Keep typing your search criteria ...',
                    on_enter=DoNothingAction())
            ])

        keyword = event.get_keyword()

        # Find the keyword id using the keyword (since the keyword can be changed by users)
        keyword_id = None
        for kw_id, kw in list(extension.preferences.items()):
            if kw == keyword:
                keyword_id = kw_id
                break

        file_type = FILE_SEARCH_ALL
        if keyword_id == "ff_kw":
            file_type = FILE_SEARCH_FILE
        elif keyword_id == "fd_kw":
            file_type = FILE_SEARCH_DIRECTORY

        results = extension.search(query.strip(), file_type)

        if not results:
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='No Results found matching %s' % query,
                    on_enter=HideWindowAction())
            ])

        items = []
        try:
            max_results = int(extension.preferences.get('max_results', '15'))
        except (TypeError, ValueError):
            max_results = 15

        for result in results[:max_results]:
            items.append(
                ExtensionResultItem(
                    icon=result['icon'],
                    name=result['path'],
                    on_enter=OpenAction(result['path']),
                    # Alt+Enter：用默认文件管理器打开所在位置
                    on_alt_enter=extension.get_open_in_file_manager_action(result['path'])
                )
            )

        return RenderResultListAction(items)


if __name__ == '__main__':
    FileSearchExtension().run()
