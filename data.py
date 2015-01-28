#! /usr/bin/env python3

import csv
import sys
from io import TextIOWrapper
from tkinter import Tk, TclError
from tkwrap import Tree, scroll
from functions import attributes
from warnings import warn
from net import PersistentConnectionHandler, http_get
import urllib.request
from xml.etree import ElementTree
import urllib.parse
from shorthand import floordiv, ceildiv
from misc import UnicodeMap

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ATOM_TYPES = ("application/atom+xml", "text/xml", "application/xml")
OPEN_SEARCH_NS = "{http://a9.com/-/spec/opensearchrss/1.0/}"
SHEET_SCHEMA = "http://schemas.google.com/spreadsheets/2006"
LIST_REL = urllib.parse.urljoin(SHEET_SCHEMA, "#listfeed")
CELLS_REL = urllib.parse.urljoin(SHEET_SCHEMA, "#cellsfeed")
GOOGLE_SHEET_NS = "{{{}}}".format(SHEET_SCHEMA)
GOOGLE_XSHEET_NS = "{{{}/extended}}".format(SHEET_SCHEMA)

def main():
    with PersistentConnectionHandler(timeout=100) as connection:
        session = urllib.request.build_opener(connection)
        
        worksheets = "https://spreadsheets.google.com/feeds/worksheets/"
        key = "1VJzt-EuvEc5b9gKzhvbekYgnXSDpXiWMt_BXp-mSmms"
        url = urljoin_path(worksheets, key, "public", "basic")
        with http_get(session, url, ATOM_TYPES) as response:
            charset = response.info().get_content_charset()
            parser = ElementTree.XMLParser(encoding=charset)
            tree = ElementTree.parse(response, parser)
        [worksheet] = tree.iter(ATOM_NS + "entry")
        [title] = tree.iterfind(ATOM_NS + "title")
        title = "".join(title.itertext())
        
        [ws_title] = worksheet.iter(ATOM_NS + "title")
        ws_title = "".join(ws_title.itertext())
        [updated] = worksheet.iter(ATOM_NS + "updated")
        updated = "".join(updated.itertext())
        msg = "“{}”, “{}”, updated {}".format(title, ws_title, updated)
        print(msg, file=sys.stderr)
        
        headings = list()
        column_numbers = dict()
        expected_column = 0
        for entry in iter_feed(session, worksheet, CELLS_REL, "basic",
                (("min-row", "1"), ("max-row", "1"))):
            [address] = entry.iterfind(ATOM_NS + "title[@type='text']")
            address = "".join(address.itertext())
            if not "A1" <= address <= "Z1":
                raise ValueError(address)
            column = ord(address[0]) - ord("A")
            if column != expected_column:
                raise ValueError(column)
            
            [heading] = entry.iterfind(ATOM_NS + "content[@type='text']")
            heading = "".join(heading.itertext())
            name = heading.translate(AlnumOnlyMap()).lower()
            if column_numbers.setdefault(name, column) != column:
                raise ValueError(heading)
            headings.append(heading)
            sys.stdout.write(heading[:7])
            
            sys.stdout.write("\t")
            expected_column = column + 1
        sys.stdout.write("\n")
        
        records = 0
        for entry in iter_feed(session, worksheet, LIST_REL, "full", (
            ("orderby", "column:value"),
            #~ ("sq", 'category = "Resistor"'),
            ("sq", 'category = ""'),
        )):
            expected_column = 0
            for child in entry.iter():
                if not child.tag.startswith(GOOGLE_XSHEET_NS):
                    continue
                column = column_numbers[child.tag[len(GOOGLE_XSHEET_NS):]]
                if column < expected_column:
                    raise ValueError(column)
                sys.stdout.write("\t" * (column - expected_column))
                for text in child.itertext():
                    sys.stdout.write(text[:7])
                sys.stdout.write("\t")
                expected_column = column + 1
            sys.stdout.write("\n")
            records += 1

def iter_feed(session, worksheet, rel, projection=None, query=()):
    xpath = "{}link[@rel='{}'][@type][@href]".format(ATOM_NS, rel)
    links = worksheet.iterfind(xpath)
    [link] = (link for link in links if link.get("type") in ATOM_TYPES)
    
    url = link.get("href")
    if projection is not None:
        url = urljoin_path(url, projection)
    url = urllib.parse.urljoin(url, "?" + urllib.parse.urlencode(query))
    with http_get(session, url, ATOM_TYPES) as response:
        charset = response.info().get_content_charset()
        parser = ElementTree.XMLParser(encoding=charset)
        tree = ElementTree.parse(response, parser)
    
    return tree.iter(ATOM_NS + "entry")  # TODO: limit number of entries downloaded

def dump_tree(element, indent=""):
    nses = {
        ATOM_NS: "",
        OPEN_SEARCH_NS: "os:",
        GOOGLE_SHEET_NS: "gs:",
        GOOGLE_XSHEET_NS: "gsx:",
    }
    [ns, tag] = element.tag.rsplit("}", 1)
    attrib = sorted(element.attrib.items())
    attrib = "".join(" {}={!r}".format(*item) for item in attrib)
    print(indent + nses[ns + "}"] + tag + attrib)
    if element.text:
        print(indent + "  " + repr(element.text))
    for child in element:
        dump_tree(child, indent + "  ")
    if element.tail:
        print(indent + repr(element.tail))

@attributes(param_types=dict(start=int, end=int, models_end=int))
def leds(start=2, end=None, *, models=None, models_end=None):
    if models is None:
        import os.path
        models = os.path.expanduser("~/proj/light/leds-models.csv")
    sys.stdin = open("~/proj/light/leds-models.csv")
    
    model_data = dict()
    with open(models, newline="") as reader:
        reader = csv.DictReader(reader)
        row = 2
        for record in reader:
            if models_end is not None and row >= models_end:
                break
            set = model_data.setdefault(record["Part"], record)
            if set is not record:
                message = "Duplicate models record for part {!r} at row {}"
                warn(message.format(record["Part"], row))
            row += 1
        else:
            if models_end is not None and row < models_end:
                warn("Models records stopped early, at row {}".format(row))
    
    tk = Tk()
    
    encoding = sys.stdin.encoding
    errors = sys.stdin.errors
    line_buffering = sys.stdin.line_buffering
    sys.stdin = TextIOWrapper(sys.stdin.detach(), encoding, errors,
        newline="", line_buffering=line_buffering)
    
    reader = csv.reader(sys.stdin)
    headings = next(reader) + ["A"]
    columns = (dict(heading=heading, width=10) for heading in headings)
    tree = Tree(tk, tree=False, columns=columns)
    scroll(tree)
    tree.focus_set()
    
    row = 2
    for record in csv.reader(sys.stdin):
        if end is not None and row >= end:
            break
        if row >= start:
            tree.add(values=record + [model_data[record[0]]["Max. A"]])
        row += 1
    else:
        if row < start or end is not None and row < end:
            warn("Records stopped early, at row {}".format(row))
    
    tk.mainloop()

def valid_colour(widget, name, default):
    try:
        widget.winfo_rgb(name)
        return name
    except TclError:
        return default

def urljoin_path(base, *segments):
    segments = (urllib.parse.quote(segment, safe=()) for segment in segments)
    return urllib.parse.urljoin(base, "/".join(segments))

class AlnumOnlyMap(UnicodeMap):
    def map_char(self, char):
        if char.isalnum():
            return char
        else:
            return None

if __name__ == "__main__":
    import clifunc
    clifunc.run()
