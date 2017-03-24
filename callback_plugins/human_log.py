#!/usr/bin/env python
# -*- coding: utf-8 -*-

import StringIO
import collections
import copy
import yaml

from ansible import constants as C
from ansible.parsing.yaml.dumper import AnsibleDumper
from ansible.plugins.callback.default import CallbackModule as CallbackModule_default
from ansible.module_utils._text import to_bytes
from ansible.utils.color import stringc
from ansible.vars.unsafe_proxy import AnsibleUnsafeText


class LiteralText(unicode): pass


class MyDumper(AnsibleDumper):

    def __init__(self, *a, **kw):
        AnsibleDumper.__init__(self, *a, default_flow_style=False, **kw)

    def process_scalar(self):
        if isinstance(self.event.value, LiteralText):
            return self.process_literal_text()
        return AnsibleDumper.process_scalar(self)

    def check_simple_key(self):
        if isinstance(self.event, yaml.events.ScalarEvent):
            if self.analysis is None:
                self.analysis = self.analyze_scalar(self.event.value)
        if self.analysis and self.analysis.scalar and isinstance(self.analysis.scalar, LiteralText):
            return True
        return AnsibleDumper.check_simple_key(self)

    def process_literal_text(self):
        if self.analysis is None:
            self.analysis = self.analyze_scalar(self.event.value)
        if self.style is None:
            self.style = self.choose_scalar_style()
        split = (not self.simple_key_context)
        if "\n" in self.analysis.scalar:
            self.write_literal(self.analysis.scalar)
        else:
            self.write_plain(self.analysis.scalar, split)

        self.analysis = None
        self.style = None

    def represent_scalar(self, tag, value, style=None):
        def should_use_block(value):
            if isinstance(value, LiteralText):
                return True
            for c in u"\u000a\u000d\u001c\u001d\u001e\u0085\u2028\u2029\n\r":
                if c in value:
                    return True
            return False

        if style is None:
            if should_use_block(value):
                style='|'
            else:
                style = self.default_style

        if not isinstance(value, LiteralText):
            value = value.splitlines(True)
            for n, v in enumerate(value[:]):
                if v.endswith(" \n"):
                    while v.endswith(" \n"):
                        v = v[:-2] + "\n"
                elif v.endswith(" "):
                    while v.endswith(" "):
                        v = v[:-1]
                value[n] = v
            value = "".join(value)

        node = yaml.representer.ScalarNode(tag, value, style=style)
        if self.alias_key is not None:
            self.represented_objects[self.alias_key] = node
        return node

    def represent_dict(self, data):
        return self.represent_mapping(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            data.items()
        )

    def represent_ansitext(self, data):
        return data


MyDumper.add_representer(
    collections.OrderedDict,
    lambda d, data: d.represent_dict(data)
)

MyDumper.add_representer(
    AnsibleUnsafeText,
    lambda d, data: d.represent_scalar('tag:yaml.org,2002:str', data)
)

MyDumper.add_representer(
    LiteralText,
    lambda d, data: d.represent_scalar('tag:yaml.org,2002:str', data)
)


def indent(text, with_):
    text = "".join([with_ + s for s in text.splitlines(True)])
    return text


def human_log(res, task, host, color, indent_with="  ", prefix="", is_handler=False):
    res = copy.deepcopy(res)
    task = copy.deepcopy(task)
    item = None

    if hasattr(res, "get"):
        if res.get("invocation"):
            if res.get("invocation").get("module_name") == "setup":
                if res.get("ansible_facts"):
                    for elm in ['ansible_facts', "_ansible_verbose_override"]:
                        if elm in res:
                            del res[elm]
        if res.get("_ansible_no_log"):
            res = "Censored.  The play deliberately requested no information be logged."
        elif "_ansible_no_log" in res:
            del res["_ansible_no_log"]
        item = res.get("item")
        if item is not None:
            del res["item"]
        for x in ['stdout', 'stderr']:
            if x in res and res.get(x):
                res[x] = LiteralText(res[x])
            elif x in res:
                del res[x]
        unreachable = bool(res.get("unreachable"))
        skipped = bool(res.get("skipped"))
        failed = bool(res.get("failed"))
        for o, n in [("_ansible_notify", "notified")]:
            if o in res:
                res[n] = res[o]
                del res[o]
        if "warnings" in res and not res["warnings"]:
            del res["warnings"]
        for banned in ["invocation", "stdout_lines", "stderr_lines",
                       "changed", "failed", "skipped", "unreachable",
                       "_ansible_delegated_vars", "_ansible_parsed",
                       "_ansible_item_result"]:
            if banned in res:
                del res[banned]

        if unreachable:
            res = res["msg"]
        elif skipped:
            res = res["skip_reason"]
        elif failed:
            if len(res) == 1:
                res = res[res.keys()[0]]

    if item is not None and not isinstance(item, list):
        try:
            res = collections.OrderedDict({host: {item: res}})
        except TypeError:
            res = collections.OrderedDict({host: {str(item): res}})
    else:
        if res:
            res = collections.OrderedDict({host: res})
        else:
            res = host
    banner = task.get_name()
    if ":" in banner:
        banner = banner.replace(u":", u"—")
    if is_handler:
        type = "handler"
    else:
        type = "task"
    if task.get_path():
        path = " @ " + task.get_path()
    else:
        path = ""
    banner = banner + stringc(" (%s%s)" % (type, path), color="bright gray")
    if prefix:
        banner = prefix + " " + banner
    if isinstance(res, basestring):
        res = LiteralText(stringc(res, color))
    elif len(res) == 1 and hasattr(res, "items"):
        k ,v = res.keys()[0], res.values()[0]
        del res[k]
        if hasattr(v, "items"):
            v = dict((LiteralText(stringc(x, color)), y) for x, y in v.items())
        res[LiteralText(stringc(k, color))] = v
    banner = LiteralText(stringc(banner, color))
    res = {banner: res}
    c = StringIO.StringIO()
    d = MyDumper(c)
    d.open()
    d.represent(res)
    d.close()
    c.seek(0)
    res_text = c.read().strip()
    if indent_with:
        res_text = indent(res_text, indent_with)
    return res_text


class CallbackModule(CallbackModule_default):

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'stdout'
    CALLBACK_NAME = 'human_log'

    def __init__(self, *args, **kwargs):
        CallbackModule_default.__init__(self, *args, **kwargs)
        self.__handlers = {}

    def _process_items(self, result):
        pass

    def v2_on_file_diff(self, result):
        return

    def v2_playbook_on_task_start(self, task, is_conditional):
        pass

    def _hostname(self, result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if delegated_vars:
            hostname = "%s <- %s" % (delegated_vars['ansible_host'], result._host.get_name())
        else:
            hostname = "%s" % (result._host.get_name(),)
        return hostname

    def v2_runner_on_failed(self, result, ignore_errors=False):
        prefix = u"\u2718"
        if 'exception' in result._result:
            msg = "An exception occurred during task execution. The full traceback is:\n" + result._result['exception']
            self._display.display(human_log(msg, result._task,
                                            hostname, C.COLOR_ERROR, prefix=prefix))

        if result._task.loop and 'results' in result._result:
            self._process_items(result)
        else:
            hostname = self._hostname(result)
            if ignore_errors:
                prefix = u"\u2718 (ignored)"
            self._display.display(human_log(result._result, result._task,
                                            hostname, C.COLOR_ERROR, prefix=prefix))

    def v2_runner_on_ok(self, result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        color = C.COLOR_CHANGED if result._result.get('changed', False) else C.COLOR_OK
        prefix = u"\u21BA" if result._result.get('changed', False) else u'\u2713'

        if 'diff' in result._result and result._result['diff']:
            if result._result.get('changed', False):
                diff = self._get_diff(result._result['diff'])
                result._result['diff'] = diff
                if isinstance(result._result['diff'], basestring):
                    result._result['diff'] = LiteralText("".join(result._result['diff']))
            if hasattr(result._result['diff'], "get"):
                if result._result['diff'].get("before") and result._result['diff'].get("after"):
                    if result._result['diff'].get("before") == result._result['diff'].get("after"):
                        del result._result['diff']['before']
                        del result._result['diff']['after']
                if not result._result['diff']:
                    del result._result['diff']

        if result._task.loop and 'results' in result._result:
            self._process_items(result)
        else:
            hostname = self._hostname(result)
            self._display.display(human_log(result._result, result._task,
                                            hostname, color, prefix=prefix,
                                            is_handler=result._task in self.__handlers))

        # FIXME: incorporate these into the pseudo-YAML format.
        self._handle_warnings(result._result)

    def v2_runner_on_skipped(self, result):
        if result._task.loop and 'results' in result._result:
            self._process_items(result)
        else:
            prefix = u"\u23E9"
            hostname = self._hostname(result)
            self._display.display(human_log(result._result, result._task,
                                            hostname, color=C.COLOR_SKIP, prefix=prefix))

    def v2_runner_on_unreachable(self, result):
        prefix = u"\U0001F6C7"
        hostname = self._hostname(result)
        self._display.display(human_log(result._result, result._task,
                                        hostname, color=C.COLOR_UNREACHABLE, prefix=prefix))

    def v2_playbook_on_play_start(self, play):
        name = play.get_name().strip()
        if not name:
            msg = u"Play:"
        else:
            msg = u"Play on %s:" % name
        self._display.display(msg, C.COLOR_VERBOSE)
        self._play = play

    def v2_playbook_on_handler_task_start(self, task):
        self.__handlers[task] = True

    def v2_runner_item_on_ok(self, result):
        self.v2_runner_on_ok(result)

    def v2_runner_item_on_failed(self, result):
        self.v2_runner_on_failed(result)

    def v2_runner_item_on_skipped(self, result):
        self.v2_runner_on_skipped(result)

#    def v2_playbook_on_include(self, included_file):
#        msg = '    for: %s' % (", ".join([h.name for h in included_file._hosts]), )
#        color = 'bright gray'
#        self._display.display(msg, color=color)
