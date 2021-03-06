######
 # Copyright 2016-present Mori, Inc.
 #
 # 
 ######

import os
import re
import json
import sublime, sublime_plugin
import time

HAS_REL_PATH_RE = re.compile(r"\.?\.?\/");
reqUpperTabbed = re.compile("(?:\/\/)?(?:\/\*)?(?: )*var [A-Z]\w*(?: )=(?: )(?:app)?[rR]equire\('[^ ']*'\)(?:\.[\w]*)?;(?: *)(?:\*\/)?(?: *)");
reqLowerTabbed = re.compile("(?:\/\/)?(?:\/\*)?(?: )*var [a-z]\w*(?: )=(?: )(?:app)?[rR]equire\('[^ ']*'\)(?:\.[\w]*)?;(?: *)(?:\*\/)?(?: *)");
reqUpper = re.compile("(?:\/\/ *)?(?:\/\* *)?var [A-Z]\w*(?: )=(?: )(?:app)?[rR]equire\('[^ ']*'\)(?:\.[\w]*)?;(?: *)(?:\*\/)?(?: *)");
reqLower = re.compile("(?:\/\/ *)?(?:\/\* *)?var [a-z]\w*(?: )=(?: )(?:app)?[rR]equire\('[^ ']*'\)(?:\.[\w]*)?;(?: *)(?:\*\/)?(?: *)");
esLintLine = re.compile("^\/\* eslint-disable.*\*\/$");
reqName = re.compile(".*var (\w*).*");
tabLength = re.compile("^( *).*$");
specialChar = re.compile("([^\W\d_]+)(\d*)([\W_]?)([\w]?)(.*)");
globalExportLine = re.compile("^(var|function) ([\w]*)");
moduleExportLine = re.compile("(module\.)?exports\.[\w]* ?= ?([\w]*);");

SETTINGS_FILE = "MoriPlugin.sublime-settings";

def get_pref(pref):
  return sublime.load_settings(SETTINGS_FILE).get(pref);

class ModuleLoader():
  def __init__(self, file_name):
    """Constructor for ModuleLoader."""
    self.file_name = file_name
    self.project_folder = self.get_project_folder()

    # If there is no package.json, show error
    if not self.has_package():
      return sublime.error_message(
        'You must have a package.json and or bower.json file '
        'in your projects root directory'
      )

  def get_project_folder(self) -> str:
    """Get the root project folder."""
    # Walk through directories if we didn't find it easily
    dirname = os.path.dirname(self.file_name)
    while dirname:
      pkg = os.path.join(dirname, 'package.json')
      if os.path.exists(pkg):
        return dirname
      parent = os.path.abspath(os.path.join(dirname, os.pardir))
      if parent == dirname:
        break
      dirname = parent

    try:
      project_data = sublime.active_window().project_data()
      if project_data:
        first_folder = project_data['folders'][0]['path']
        return first_folder
    except:
      pass

  def has_package(self):
    """Check if the package.json is in the project directory."""
    return os.path.exists(
      os.path.join(self.project_folder, 'package.json')
    )

  def get_file_list(self):
    """Return the list of dependencies and local files."""
    files = self.get_local_files() + self.get_dependencies()
    
    return files

  def get_local_files(self):
    """Load the list of local files."""
    # Don't throw errors if invoked in a view without
    # a filename like the console
    local_files = []
    if not self.file_name:
      return []

    dirname = os.path.dirname(self.file_name)
    for root, dirs, files in os.walk(self.project_folder, topdown=True):
      if os.path.samefile(root, self.project_folder):
        exclude = get_pref('excludeDirs');
        dirs[:] = [d for d in dirs if d not in exclude]

      for file_name in files:
        if file_name[0] is not '.':
          file_name = "%s/%s" % (root, file_name)
          file_name = os.path.relpath(file_name, self.project_folder)

          if file_name == os.path.basename(self.file_name):
            continue

          if not HAS_REL_PATH_RE.match(file_name):
            file_name = "./%s" % file_name

        if file_name[0] is '.' and file_name[1] is not '/':
          continue;

        ext = os.path.splitext(file_name)[1];
        if not ext in get_pref('extensions'):
          continue;

        local_files.append([os.path.basename(file_name), file_name])
    return local_files

  def get_dependencies(self):
    """Parse the package.json file into a list of dependencies."""
    package = os.path.join(self.project_folder, 'package.json')
    package_json = json.load(open(package, 'r', encoding='UTF-8'))
    dependency_types = {
      'dependencies': 'project module',
      'devDependencies': 'dev module',
      'optionalDependencies': 'optional module',
      'electronDependencies': 'electron module',
    }
    dependencies = self.get_dependencies_with_type(
      dependency_types, package_json
    );

    cores = get_pref('core_modules');
    for i in range(0,len(cores), 1):
      dependencies.append([cores[i], cores[i]]);

    return dependencies;

  def get_dependencies_with_type(self, dependency_types, json):
        """Common function for adding dependencies (bower or package.json)."""
        dependencies = []
        for dependency_type in dependency_types:
            if dependency_type in json:
                keys = json[dependency_type].keys();
                for key in keys:
                  listingElement = [element for element in dependencies if element[0] == key]
                  if len(listingElement):
                    continue;
                  else:
                    dependencies.append([key, key]);
        return dependencies

class appRequireDocCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    self.module_loader = ModuleLoader(self.view.file_name());
    self.files = self.module_loader.get_file_list();
    sublime.active_window().show_quick_panel(
      self.files, self.on_done_call_func(self.files, self.insertAppRequire));

  def insertAppRequire(self, fileEntry):
    module = fileEntry[1];
    pos = self.view.find("^'use strict';$", 0).end();

    if pos == -1:
      pos = 0;
    else:
      pos+=1;

    lastGoodPos = pos;
    pad = 0;

    cores = get_pref('core_modules');
    isCore = module in cores;

    while (pos < self.view.size()):
      area = self.view.line(pos);
      line = self.view.substr(area);

      if isCore:
        if re.match(reqLower, line):
          break;

        if re.match(reqUpper, line):
          pos = lastGoodPos;
          pad = 1;
          break;

        if re.match(esLintLine, line):
          lastGoodPos = area.end()+1;

      else:
        if re.match(reqUpper, line):
          break;

        if re.match(reqLower, line) or re.match(esLintLine, line):
          lastGoodPos = area.end()+1;

      pos = area.end()+1;

    if pos >= self.view.size():
      pos = lastGoodPos;
      pad = 1;

    self.view.run_command('app_require_insert_helper', {
      'args': {
        'module': module,
        'pos':pos,
        'highlight':0,
        'pad':pad,
      }
    });

  def on_done_call_func(self, choices, func):
    """Return a function which is used with sublime list picking."""
    def on_done(index):
        if index >= 0:
            return func(choices[index])

    return on_done

class appRequireCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    self.module_loader = ModuleLoader(self.view.file_name())
    self.files = self.module_loader.get_file_list()
    sublime.active_window().show_quick_panel(
      self.files, self.on_done_call_func(self.files, self.insertAppRequire));

  def insertAppRequire(self, fileEntry):
    module = fileEntry[1];
    self.view.run_command('app_require_insert_helper', {
      'args': {
        'module': module,
        'pos': self.view.sel()[0].begin(),
        'highlight':1,
        'pad':0,
      }
    });
    

  def on_done_call_func(self, choices, func):
    """Return a function which is used with sublime list picking."""
    def on_done(index):
        if index >= 0:
            return func(choices[index])

    return on_done

class appRequireInsertHelper(sublime_plugin.TextCommand):
  def varNameFromModule(self, module):
    cores = get_pref('core_modules');
    inCore = module in cores;
    
    ext = os.path.splitext(module)[1];

    if (module.rfind('/') != -1):
      module = module[module.rfind('/')+1:];

    if (module.find('.') != -1):
      module = module[:module.find('.')];

    count=0;
    while count<100: #avoid infinate loop
      match = re.search(specialChar, module);
      if (match):
        module = match.group(1) + match.group(2) + match.group(4).upper() + match.group(5);
        count+=1;
      else:
        break;

    
    if inCore == False:
      #cap first letter of any dependencies or files
      module = module[0].upper() + module[1:];
    
    #check for any alias
    aliasCheck = get_pref('alias');

    for alias in aliasCheck:
      aliasCheck[alias] = {
        "regex": re.compile(alias),
        "changes": aliasCheck[alias],
      }

    for alias in aliasCheck:
      m = re.match(aliasCheck[alias]["regex"], module);
      if m:
        for i in range(len(aliasCheck[alias]["changes"])-1,-1,-1):
          module = module[:m.start(i+1)] + aliasCheck[alias]["changes"][i] + module[m.end(i+1):];
        break;
    
    prefix = get_pref('prefix');
    if ext in prefix:
      module = prefix[ext] + module;

    return module;

  def moduleNameFromLine(self, line):
    line = line.lower();
    match = re.match(reqName, line);
    if match:
      return match.group(1);
    else:
      return line;

  def run (self, edit, args):
    view = self.view
    module = args['module'];
    pos = args['pos'];

    entry = "require('" + module + "');";

    if module[-3:] == '.js':
      module = module[:-3];

    if module[0] == '.':
      entry = "appRequire('" + module[2:] + "');";

    if (module[0] == '/'):
      entry = "appRequire('" + module[1:] + "');";

    linepos = view.line(pos);
    line = view.substr(linepos);
    tabs = re.match(tabLength, line);

    if (tabs):
      tabs = tabs.group(1);
    else:
      tabs = '';

    cores = get_pref('core_modules');
    if module in cores:
      reqLine = reqLowerTabbed;
    else:
      reqLine = reqUpperTabbed;

    if line.strip() == '' or re.match(reqLine, line):
      
      entry = tabs + 'var ' + self.varNameFromModule(module) + ' = ' + entry;
      lines = [entry];
      idx = linepos.a-1;
      replace = linepos;

      if re.match(reqLine, line):
        lines.append(line);

      if args['pad']==0:
        while idx>=0:
          line = view.substr(view.line(idx));
          if re.match(reqLine, line):
            lines.append(line);
            replace = replace.cover(view.line(idx));
            idx = view.line(idx).begin()-1;

          else:
            break;

        idx = linepos.b+1;
        while idx<self.view.size():
          line = view.substr(view.line(idx));
          if (re.match(reqLine, line)):
            lines.append(line);
            replace = replace.cover(view.line(idx));
            idx = view.line(idx).end()+1;
          else:
              break;

      lines = sorted(set(lines), key=self.moduleNameFromLine);

      if args['pad']:
        lines.append('');
        lines.insert(0, '');
      
      self.view.replace(edit, replace, '\n'.join(str(x) for x in lines));

      if args['highlight'] == 1:
        findLine = entry.strip();
        higlight = self.view.find(findLine, replace.begin(), sublime.LITERAL);
        self.view.sel().clear();
        self.view.sel().add(higlight);
    else:
      self.view.insert(edit, pos, entry);

class insertMoriCopyright(sublime_plugin.TextCommand):
  def run (self, edit):
    self.view.insert(edit, 0, "/**\n * Copyright " + time.strftime('%Y') + "-present Mori, Inc.\n *\n */\n'use strict';");

class insertExportLine(sublime_plugin.TextCommand):
  def run (self, edit):
    view = self.view;
    size = view.size();
    pos = 0;
    lineNum = 1;
    lines = [];
    cursor = self.view.sel();
    select = 0;

    while pos < size:
      area = self.view.line(pos);
      line = self.view.substr(area);
      match = re.match(globalExportLine, line);
      if (match and line.find('appRequire') == -1 and line.find('require') == -1):
        c=0;
        while c<len(cursor):
          if (area.intersects(cursor[c])):
            select = len(lines);
          c += 1;
        lines.append([match.group(2), str(lineNum) + ': ' +line]);
      pos += area.size()+1;
      lineNum += 1;

    sublime.active_window().show_quick_panel(
      lines, self.on_done_call_func(lines, self.insertExportLine), 0, select);

  def on_done_call_func(self, choices, func):
    """Return a function which is used with sublime list picking."""
    def on_done(index):
        if index >= 0:
            return func(choices[index])

    return on_done

  def insertExportLine(self, line):
    self.view.run_command('export_insert_helper', {
      'args': {
        'export': line[0],
      }
    });

class exportInsertHelper(sublime_plugin.TextCommand):
  def run (self, edit, args):
    toExport = args['export'];
    view = self.view;
    size = view.size();
    pos = 0;
    lastExportPos = size;
    useModule = False;
    
    while pos < size:
      area = self.view.line(pos);
      line = self.view.substr(area);
      match = re.match(moduleExportLine, line);
      
      if (match):
        lastExportPos = area.end();
        if (match.group(2) == toExport):
          return;
        if (match.group(1)):
          useModule = True;
      pos = area.end()+1;

    if (useModule):
      toExport = '\nmodule.exports.' + toExport + ' = ' + toExport + ';';
    else:
      toExport = '\nexports.' + toExport + ' = ' + toExport + ';';

    self.view.insert(edit, lastExportPos, toExport);
