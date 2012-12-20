# -*- coding: utf-8 -*-
import os

import sublime
import sublime_plugin

from flake8_harobed.util import skip_line
from lint import lint, lint_external


settings = sublime.load_settings("Flake8Lint.sublime-settings")
FLAKE_DIR = os.path.dirname(os.path.abspath(__file__))
viewToRegionToErrors = {}


class Flake8LintCommand(sublime_plugin.TextCommand):
    """
    Do flake8 lint on current file.
    """
    def run(self, edit):
        """
        Run flake8 lint.
        """
        # current file name
        filename = os.path.abspath(self.view.file_name())

        # check if active view contains file
        if not filename:
            return

        # check only Python files
        if not self.view.match_selector(0, 'source.python'):
            return

        # save file if dirty
        if self.view.is_dirty():
            self.view.run_command('save')

        # try to get interpreter
        interpreter = settings.get('python_interpreter', 'auto')

        if not interpreter or interpreter == 'internal':
            # if interpreter is Sublime Text 2 internal python - lint file
            self.errors_list = lint(filename, settings)
        else:
            # else - check interpreter
            if interpreter == 'auto':
                interpreter = 'python'
            elif not os.path.exists(interpreter):
                sublime.error_message(
                    "Python Flake8 Lint error:\n"
                    "python interpreter '%s' is not found" % interpreter
                )

            # TODO: correct linter path handle
            # build linter path for Packages Manager installation
            linter = os.path.join(FLAKE_DIR, 'lint.py')

            # build linter path for installation from git
            if not os.path.exists(linter):
                linter = os.path.join(
                    sublime.packages_path(), 'Flake8Lint', 'lint.py')

            if not os.path.exists(linter):
                sublime.error_message(
                    "Python Flake8 Lint error:\n"
                    "sorry, can't find correct plugin path"
                )

            # and lint file in subprocess
            self.errors_list = lint_external(filename, settings,
                                             interpreter, linter)

        # show errors
        if self.errors_list:
            self.show_errors()

    def show_errors(self):
        """
        Show all errors.
        """
        errors_to_show = []

        # get select and ignore settings
        select = settings.get('select') or []
        ignore = settings.get('ignore') or []

        regions = []
        viewStorage = viewToRegionToErrors[self.view.id()] = {}

        errors_list_filtered = []
        for e in self.errors_list:
            # get error line
            text_point = self.view.text_point(e[0] - 1, 0)
            line = self.view.full_line(text_point)
            full_line_text = self.view.substr(line)
            line_text = full_line_text.strip()

            # skip line if 'noqa' defined
            if skip_line(line_text):
                continue

            # parse error line to get error code
            code, _ = e[2].split(' ', 1)

            # check if user has a setting for select only errors to show
            if select and filter(lambda err: not code.startswith(err), select):
                continue

            # check if user has a setting for ignore some errors
            if ignore and filter(lambda err: code.startswith(err), ignore):
                continue

            # build line error message
            error = [e[2], u'{0}: {1}'.format(e[0], line_text)]
            if error not in errors_to_show:
                errors_list_filtered.append(e)
                errors_to_show.append(error)

            indent = len(full_line_text) - len(full_line_text.lstrip())
            region = sublime.Region(text_point + indent, 
                    text_point + indent + len(line_text))
            viewStorage[region.a] = { 'error': error[0] }
            regions.append(region)

        if settings.get('highlight'):
            # It may not make much sense, but string is the best coloration,
            # as far as I can tell.
            self.view.add_regions('flake8-errors', regions, "string", "",
                    sublime.DRAW_EMPTY)

        # renew errors list with selected and ignored errors
        self.errors_list = errors_list_filtered

        if settings.get('popup'):
            # view errors window
            self.view.window().show_quick_panel(errors_to_show,
                                                self.error_selected)

    def error_selected(self, item_selected):
        """
        Error was selected - go to error.
        """
        if item_selected == -1:
            return

        # reset selection
        selection = self.view.sel()
        selection.clear()

        # get error region
        error = self.errors_list[item_selected]
        region_begin = self.view.text_point(error[0] - 1, error[1])

        # go to error
        selection.add(sublime.Region(region_begin, region_begin))
        self.view.show_at_center(region_begin)


class Flake8LintBackground(sublime_plugin.EventListener):
    """
    Listen to Siblime Text 2 events.
    """
    def on_post_save(self, view):
        """
        Do lint on file save if not denied in settings.
        """
        if settings.get('lint_on_save', True):
            view.run_command('flake8_lint')


    def on_selection_modified(self, view):
        regs = view.get_regions('flake8-errors')
        selLine = view.line(view.sel()[0])
        viewStorage = viewToRegionToErrors.get(view.id())
        if viewStorage is None:
            return
        tip = []
        for reg in regs:
            if reg.intersects(selLine):
                tip.append(viewStorage.get(reg.a, {}).get('error', 
                        '(Unrecognized)'))

        if tip:
            view.set_status('flake8-tip', ' / '.join(tip))
        else:
            view.erase_status('flake8-tip')
