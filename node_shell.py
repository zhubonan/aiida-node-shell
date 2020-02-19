#!/usr/bin/env runaiida
"""
This is a proof of concept of a `verdi node shell` command to easily browse AiiDA nodes
through an interactive, customisable shell with tab completion.

Expected use-case: quick browsing of node attributes, extras and files in the repository,
with faster interface (node pre-loaded, very fast tab-completion, ...) than `verdi` and
a much more intuitive interface (even if more limited) than the python API.

More details in the README.md file.

Author: Giovanni Pizzi, EPFL

Version: 0.1
"""
import cmd2
import functools
from datetime import datetime
import pytz
import sys

from ago import human
import click

from aiida.common.links import LinkType
from aiida.orm.utils.repository import FileType
from pprint import pformat

# Examples for autocompletion: https://github.com/python-cmd2/cmd2/blob/master/examples/tab_autocompletion.py

LINK_TYPES_DICT = {link_type.value.upper(): link_type for link_type in LinkType}

LINK_TYPES = sorted(LINK_TYPES_DICT.keys())

def with_default_argparse(f):
    """Decorator to use the default argparse parser (e.g. provide -h)."""
    return cmd2.with_argparser(cmd2.Cmd2ArgumentParser())(f)

def now_aware():
    """Get the current datetime object, aware of the timezone (in UTC)."""
    return datetime.utcnow().replace(tzinfo=pytz.utc)

def needs_node(f):
    """Decorator to add to a command if it needs to have a node loaded to work.
    
    It performs validation that the node is there, and prints a suitable error if this is not the case."""
    @functools.wraps(f)
    def wrapper(self, *args, **kwds): # pylint: disable=inconsistent-return-statements
        """Print an error and return if there is no node loaded."""
        if not self._current_node:  # pylint: disable=protected-access
            print("ERROR: No node loaded - load a node with `load NODE_IDENTIFIER` first")
            return
        return f(self, *args, **kwds)

    return wrapper


class AiiDANodeShell(cmd2.Cmd):
    """An interactive shell to browse node and their properties (attributes, extras, repository files, ...)."""
    intro = 'AiiDA node shell. Type help or ? to list commands.\n'
    _current_node = None
    _current_profile = None

    def __init__(self, *args, node_identifier=None, **kwargs):
        """Initialise a shell, possibly with a given node preloaded."""
        super().__init__(*args, **kwargs)
        if node_identifier:
            self._set_current_node(node_identifier)

    def _set_current_node(self, identifier):
        """Set a node from an identifier."""
        from aiida.orm.utils.loaders import NodeEntityLoader

        self._current_node = NodeEntityLoader.load_entity(identifier)

    @property
    def current_profile(self):
        """Return a string with the current profile name (or 'NO_PROFILE' if no profile is loaded)."""
        from aiida.manage.configuration import get_config
        
        # Caching
        if not self._current_profile:
            current_profile = get_config().current_profile
            if current_profile:
                self._current_profile = current_profile.name

        if not self._current_profile:
            return "NO_PROFILE"

        return self._current_profile

    def _get_node_string(self):
        """Return a string representing the current node (to be used in the prompt)."""
        if self._current_node is None:
            return ''
        class_name = self._current_node.__class__.__name__
        identifier = self._current_node.pk
        return '{}<{}>'.format(class_name, identifier)

    @property
    def prompt(self):
        """Define a custom prompt string."""
        if self._current_node:
            return '({}@{}) '.format(self._get_node_string(), self.current_profile)
        return '({}) '.format(self.current_profile)

    def do_load(self, arg):
        """Load a node in the shell, making it the 'current node'."""
        self._set_current_node(arg)

    @needs_node
    @with_default_argparse
    def do_uuid(self, arg):  # pylint: disable=unused-argument
        """Show the UUID of the current node."""
        print(self._current_node.uuid)

    @needs_node
    @with_default_argparse
    def do_label(self, arg):  # pylint: disable=unused-argument
        """Show the label of the current node."""
        print(self._current_node.label)

    @needs_node
    @with_default_argparse
    def do_description(self, arg):  # pylint: disable=unused-argument
        """Show the description of the current node."""
        print(self._current_node.description)

    @needs_node
    @with_default_argparse
    def do_ctime(self, arg):  # pylint: disable=unused-argument
        """Show the creation time of the current node."""
        ctime = self._current_node.ctime
        print("Created {} ({})".format(human(now_aware() - ctime), ctime))

    @needs_node
    @with_default_argparse
    def do_mtime(self, arg):  # pylint: disable=unused-argument
        """Show the last modification time of the current node."""
        mtime = self._current_node.mtime
        print("Last modified {} ({})".format(human(now_aware() - mtime), mtime))

    @needs_node
    @with_default_argparse
    def do_extras(self, arg):  # pylint: disable=unused-argument
        """Show all extras of the current node (keys and values)."""
        extras = self._current_node.extras
        if not extras:
            print("No extras")
            return
        for key, val in extras.items():
            print('- {}: {}'.format(key, pformat(val)))


    def extras_choices_method(self):
        """Method that returns all possible values for the 'extras' command, used for tab-completion."""
        completions_with_desc = []

        extras_keys = self._current_node.extras_keys()
        for key in extras_keys:
            completions_with_desc.append(cmd2.CompletionItem(key, "({})".format(type(self._current_node.get_extra(key)).__name__)))

        # Mark that we already sorted the matches
        # self.matches_sorted = True
        return completions_with_desc

    extrakey_parser = cmd2.Cmd2ArgumentParser()
    extrakey_parser.add_argument('extra_key', help='The extra key',
        choices_method=extras_choices_method)

    @needs_node
    @cmd2.with_argparser(extrakey_parser)
    def do_extra(self, arg):
        """Show one extra of the current node."""
        extras = self._current_node.extras
        try:
            print('- {}: {}'.format(arg.extra_key, pformat(extras[arg.extra_key])))
        except KeyError:
            print("No extra with key '{}'".format(arg.extra_key))

    @needs_node
    @with_default_argparse
    def do_extrakeys(self, arg):  # pylint: disable=unused-argument
        """Show the keys of all extras of the current node."""
        extras_keys = self._current_node.extras_keys()
        if not extras_keys:
            print("No extras")
            return
        for key in sorted(extras_keys):
            print('- {}'.format(key))

    @needs_node
    @with_default_argparse
    def do_attrs(self, arg):  # pylint: disable=unused-argument
        """Show all attributes (keys and values) of the current node."""
        attributes = self._current_node.attributes
        if not attributes:
            print("No attributes")
            return
        for key, val in attributes.items():
            print('- {}: {}'.format(key, pformat(val)))

    def attrs_choices_method(self):
        """Method that returns all possible values for the 'attrs' command, used for tab-completion."""
        completions_with_desc = []

        attributes_keys = self._current_node.attributes_keys()
        for key in attributes_keys:
            #if key.startswith(text):
            completions_with_desc.append(cmd2.CompletionItem(key, "({})".format(type(self._current_node.get_attribute(key)).__name__)))

        # Mark that we already sorted the matches
        # self.matches_sorted = True
        return completions_with_desc

    attrkey_parser = cmd2.Cmd2ArgumentParser()
    attrkey_parser.add_argument('attribute_key', help='The attribute key',
        choices_method=attrs_choices_method)

    @needs_node
    @cmd2.with_argparser(attrkey_parser)
    def do_attr(self, arg):
        """Show one attribute of the current node."""
        attributes = self._current_node.attributes
        try:
            print('- {}: {}'.format(arg.attribute_key, pformat(attributes[arg.attribute_key])))
        except KeyError:
            print("No attribute with key '{}'".format(arg.attribute_key))

    @needs_node
    @with_default_argparse
    def do_attrkeys(self, arg):  # pylint: disable=unused-argument
        """Show the keys of all attributes of the current node."""
        attributes_keys = self._current_node.attributes_keys()
        if not attributes_keys:
            print("No attributes")
            return
        for key in sorted(attributes_keys):
            print('- {}'.format(key))

    link_parser = cmd2.Cmd2ArgumentParser()
    link_parser.add_argument('-t', '--link-type', help='Filter by link type',
        choices=LINK_TYPES)

    @needs_node
    @cmd2.with_argparser(link_parser)
    def do_in(self, arg):
        """List all nodes connected with incoming links to the current node. 
        
        The command also allows to filter by link type."""
        type_filter_string = ''
        if arg.link_type is None:
            incomings = self._current_node.get_incoming().all()
        else:
            incomings = self._current_node.get_incoming(link_type=LINK_TYPES_DICT[arg.link_type]).all()
            type_filter_string = ' of type {}'.format(arg.link_type)
        if not incomings:
            print("No incoming links{}".format(type_filter_string))
            return
        for incoming in incomings:
            print("- {} ({}) -> {}".format(incoming.link_type.value.upper(), incoming.link_label, incoming.node.pk))
        
    @needs_node
    @cmd2.with_argparser(link_parser)
    def do_out(self, arg):
        """List all nodes connected with outgoing links to the current node. 
        
        The command also allows to filter by link type."""
        type_filter_string = ''
        if arg.link_type is None:
            outgoings = self._current_node.get_outgoing().all()
        else:
            outgoings = self._current_node.get_outgoing(link_type=LINK_TYPES_DICT[arg.link_type]).all()
            type_filter_string = ' of type {}'.format(arg.link_type)

        outgoings = self._current_node.get_outgoing().all()
        if not outgoings:
            print("No outgoing links{}".format(type_filter_string))
            return
        for outgoing in outgoings:
            print("- {} ({}) -> {}".format(outgoing.link_type.value.upper(), outgoing.link_label, outgoing.node.pk))

    @needs_node
    @with_default_argparse 
    def do_show(self, arg):  # pylint: disable=unused-argument
        """Show textual information on the current node."""
        from aiida.cmdline.utils.common import get_node_info

        print(get_node_info(self._current_node))

    def repo_ls_completer_method(self, text, line, begidx, endidx):
        """Method to perform completion for the 'repo_ls' command.
        
        This implements custom logic to make sure it works properly for folders and ignores files."""
        folder, _, start = text.rpartition('/')
        first_level_matching = [
            folder + ('/' if folder else '') + obj.name + '/'
            for obj in self._current_node.list_objects(folder) 
            if obj.name.startswith(start) and obj.type == FileType.DIRECTORY]
        # I go down one level more to have proper completion of folders
        # without being too expensive for arbitrary-length recursion
        matching = []
        for first_level_folder in first_level_matching:
            matching.append(first_level_folder)
            matching.extend([
            first_level_folder + '/' + obj.name + '/'
            for obj in self._current_node.list_objects(first_level_folder) 
            if obj.type == FileType.DIRECTORY])

        return self.delimiter_complete(text, line, begidx, endidx, delimiter='/', 
            match_against=matching)

    def repo_cat_completer_method(self, text, line, begidx, endidx):
        """Method to perform completion for the 'repo_ls' command.
        
        This implements custom logic to make sure it works properly both for folders and for files."""
        folder, _, start = text.rpartition('/')
        first_level_matching = [
            folder + ('/' if folder else '') + obj.name + ('/' if obj.type == FileType.DIRECTORY else '')
            for obj in self._current_node.list_objects(folder) 
            if obj.name.startswith(start)]
        matching = []
        for first_level_object in first_level_matching:
            matching.append(first_level_object)
            if first_level_object.endswith('/'):
                matching.extend([
                first_level_object + '/' + obj.name + ('/' if obj.type == FileType.DIRECTORY else '')
                for obj in self._current_node.list_objects(first_level_object)])

        return self.delimiter_complete(text, line, begidx, endidx, delimiter='/', 
            match_against=matching)

    ls_parser = cmd2.Cmd2ArgumentParser()
    ls_parser.add_argument('-l', '--long', action='store_true', help="Show additional information on each object, e.g. if it's a file or a folder")
    ls_parser.add_argument('-s', '--no-trailing-slashes', action='store_true', help="Do not show trailing slashes for folders")
    ls_parser.add_argument('PATH', nargs='?', default='.', help="The path to list",
        completer_method=repo_ls_completer_method
        )
    @needs_node
    @cmd2.with_argparser(ls_parser)
    def do_repo_ls(self, arg):
        """List all files and folders in the repository of the current node."""
        for obj in self._current_node.list_objects(arg.PATH):
            if arg.long:
                click.secho('[{}] '.format(obj.type.name[0].lower()), fg='blue', bold=True, nl=False)
            click.secho(obj.name, nl=False, bold=(obj.type == FileType.DIRECTORY))
            if arg.no_trailing_slashes:
                click.secho("")
            else:
                if obj.type == FileType.DIRECTORY:
                    click.secho("/")
                else:
                    click.secho("")

    cat_parser = cmd2.Cmd2ArgumentParser()
    cat_parser.add_argument('PATH', nargs='?', default='.', help="The path to the file to output",
        completer_method=repo_cat_completer_method
        )
    @needs_node
    @cmd2.with_argparser(cat_parser)
    def do_repo_cat(self, arg):
        """Echo on screen the content of a file in the repository of the current node."""
        try:
            content = self._current_node.get_object_content(arg.PATH)
        except IsADirectoryError:
            print("Error: '{}' is a directory".format(arg.PATH), file=sys.stderr)
        except FileNotFoundError:
            print("Error: '{}' not found if node repository".format(arg.PATH), file=sys.stderr)
        else:
            sys.stdout.write(content)

    @with_default_argparse
    def do_unload(self, arg):  # pylint: disable=unused-argument
        """Unload the node from the repository, making no node to be selected as the 'current node'."""
        self._current_node = None

    @with_default_argparse
    def do_exit_with_error(self, arg):  # pylint: disable=unused-argument
        """Exit the shell with a non-zero error code.
        
        This function is mostly for internal use."""
        self.exit_code = 1
        return True

    @with_default_argparse
    def do_exit(self, arg):  # pylint: disable=unused-argument
        """Exit the shell."""
        return True

    #def precmd(self, line):
    #    'To be implemented in case we want to manipulate the line'
    #    #line = line.lower()
    #    return line

if __name__ == '__main__':
    import os

    # TODO: change this, it's not the recommended way (things written on the command line are default commands)
    try:
        node_identifier = sys.argv[1]
        sys.argv = sys.argv[1:]
    except IndexError:
        node_identifier = None
    
    try:
        shell = AiiDANodeShell(node_identifier=node_identifier, startup_script=os.path.expanduser('~/.aiidashellrc'))
    except Exception as exc:
        print("ERROR: {}: {}".format(exc.__class__.__name__, exc))
    else:

        while True:
            try:
                sys.exit(shell.cmdloop())
                break
            except KeyboardInterrupt: # CTRL+C pressed
                # Ignore CTRL+C
                print()
                print()
