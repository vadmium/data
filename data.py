#! /usr/bin/env python3

import csv
import sys
from io import TextIOWrapper, BufferedWriter, BufferedIOBase
import tkinter
from tkwrap import Tree, scroll, Form
from functions import attributes
from warnings import warn
from net import PersistentConnectionHandler, http_request
import urllib.request
from xml.etree import ElementTree
import urllib.parse
from misc import UnicodeMap
from tkinter.ttk import Frame, Entry
from xml.sax.saxutils import XMLGenerator
from xml.sax import xmlreader
from urllib.error import HTTPError
import http.client
from contextlib import closing

ATOM_NS = "http://www.w3.org/2005/Atom"
ATOM_PREFIX = "{" + ATOM_NS + "}"
ATOM_TYPES = ("application/atom+xml", "text/xml", "application/xml")
OPEN_SEARCH_NS = "http://a9.com/-/spec/opensearchrss/1.0/"
GOOGLE_SHEET_NS = "http://schemas.google.com/spreadsheets/2006"
LIST_REL = urllib.parse.urljoin(GOOGLE_SHEET_NS, "#listfeed")
CELLS_REL = urllib.parse.urljoin(GOOGLE_SHEET_NS, "#cellsfeed")
POST_REL = "http://schemas.google.com/g/2005#post"
GOOGLE_SHEETX_NS = GOOGLE_SHEET_NS + "/extended"

class main:
    def __init__(self):
        self.tk = tkinter.Tk()
        
        self.entry_var = tkinter.StringVar()
        self.entry = Entry(self.tk, textvariable=self.entry_var)
        self.entry.pack(fill=tkinter.BOTH, side=tkinter.TOP)
        self.entry.bind("<Return>", self.update_cell)
        self.entry.bind("<KP_Enter>", self.update_cell)
        
        self.login = tkinter.Toplevel(self.tk)
        self.login.bind("<Return>", self.on_login_enter)
        self.login.bind("<KP_Enter>", self.on_login_enter)
        self.login.wm_title("Log in")
        form = Form(self.login)
        self.email = Entry(self.login)
        form.add_field(self.email, text="Email")
        self.passwd = Entry(self.login, show="•")
        form.add_field(self.passwd, text="Password")
        self.email.focus_set()
        
        with PersistentConnectionHandler(timeout=100) as self.connection:
            self.session = urllib.request.build_opener(self.connection)
            self.tk.mainloop()
    
    def on_login_enter(self, event):
        if not self.passwd.get():
            self.passwd.focus_set()
            return
        print("POST", self.email.get(), end=" ", flush=True, file=sys.stderr)
        try:
            response = http_request(
                method="POST",
                url="https://www.google.com/accounts/ClientLogin",
                headers=(
                    ("Content-Type",
                        "application/x-www-form-urlencoded; charset=UTF-8"),
                ),
                data=urllib.parse.urlencode((
                    ("accountType", "HOSTED_OR_GOOGLE"),
                    ("Email", self.email.get()),
                    ("Passwd", self.passwd.get()),
                    ("service", "wise"),
                    ("source", "data.py"),
                ), encoding="utf-8").encode("ascii"),
                types=("text/plain",),
            )
        except HTTPError as err:
            if err.code != http.client.FORBIDDEN:
                raise
            print(err)
            # TODO: check content type
            properties = parse_login_response(err.headers, err)
            print(properties)
            # reason could be captcha required or incorrect username or password (text/plain)
            # * Error=CaptchaRequired; CaptchaToken=. . .; CaptchaUrl=<to be joined to http://www.google.com/accounts/>
            # * other errors; HTTP status text may not be as useful in most cases, but may be useful in some cases
            raise PermissionError(properties["Error"]) from err
        with response:
            print(response.status, response.reason,
                end="", flush=True, file=sys.stderr)
            properties = parse_login_response(response.info(), response)
        print(file=sys.stderr)
        auth = "GoogleLogin auth=" + properties["Auth"]
        self.auth = ("Authorization", auth)
        self.login.destroy()
        
        view_frame = Frame(self.tk)
        view_frame.pack(fill=tkinter.BOTH,
            side=tkinter.BOTTOM, expand=True)
        
        url = urljoin_path(
            "https://spreadsheets.google.com/feeds/worksheets/",
            "1VJzt-EuvEc5b9gKzhvbekYgnXSDpXiWMt_BXp-mSmms",
            "private",
            "basic",
        )
        worksheets = self.atom_request(url=url)
        [self.worksheet] = worksheets.iter(ATOM_PREFIX + "entry")
        [title] = worksheets.iterfind(ATOM_PREFIX + "title")
        title = "".join(title.itertext())
        self.tk.wm_title(title)
        
        [ws_title] = self.worksheet.iter(ATOM_PREFIX + "title")
        ws_title = "".join(ws_title.itertext())
        [updated] = self.worksheet.iter(ATOM_PREFIX + "updated")
        updated = "".join(updated.itertext())
        msg = "“{}”, “{}”, updated {}".format(title, ws_title, updated)
        print(msg, file=sys.stderr)
        
        headings = list()
        self.name_list = list()
        name_set = set()
        query = (("min-row", "1"), ("max-row", "1"))
        feed = self.get_feed(CELLS_REL, "basic", query)
        for entry in feed.iter(ATOM_PREFIX + "entry"):  # TODO: limit number of entries downloaded
            [address] = entry.iterfind(ATOM_PREFIX + "title[@type='text']")
            address = "".join(address.itertext())
            if not "A1" <= address <= "Z1":
                raise ValueError(address)
            column = ord(address[0]) - ord("A")
            if column != len(headings):
                raise ValueError(address)
            
            [heading] = entry.iterfind(ATOM_PREFIX + "content[@type='text']")
            heading = "".join(heading.itertext())
            name = heading.translate(AlnumOnlyMap()).lower()
            if name in name_set:
                raise ValueError(heading)
            headings.append(heading)
            self.name_list.append(name)
            name_set.add(name)
        
        self.view = Tree(view_frame, tree=False, columns=headings)
        scroll(self.view)
        self.view.bind("<Double-1>", self.on_double_click)
        self.view.bind("<Button-3>", self.on_right_click)
        
        self.edit_links = dict()
        query = (("orderby", "column:value"),)
        feed = self.get_feed(LIST_REL, "full", query)
        self.post = atom_link(feed, POST_REL)
        for entry in feed.iter(ATOM_PREFIX + "entry"):  # TODO: limit number of entries downloaded
            self.add_entry(entry)
        
        window = tkinter.Toplevel(self.tk)
        window.wm_title("Add record")
        form = Form(window)
        self.add_entries = list()
        for heading in headings:
            entry = Entry(window)
            form.add_field(entry, text=heading)
            self.add_entries.append(entry)
        if self.add_entries:
            self.add_entries[0].focus_set()
        window.bind("<Return>", self.on_add_enter)
        window.bind("<KP_Enter>", self.on_add_enter)
    
    def on_double_click(self, event):
        item = self.view.identify_row(event.y)
        column = self.view.identify_column(event.x)
        if not item or not column:
            return
        self.item = item
        self.entry_var.set(self.view.set(self.item, column))
        self.entry.selection_range(0, "end")
        self.column = int(column.lstrip("#")) - 1
        self.entry.focus_set()
    
    def on_right_click(self, event):
        column = self.view.identify_column(event.x)
        if not column:
            return
        Filter(self, column)
    
    def update_cell(self, event):
        request = self.send_atom("PUT", self.edit_links[self.item])
        with closing(request):
            xml = next(request)  # Start sending request body
            name = "gsx:" + self.name_list[self.column]
            xml.startElement(name, xmlreader.AttributesImpl(dict()))
            xml.characters(self.entry_var.get())
            xml.endElement(name)
            try:
                [entry] = request  # Finish request and receive response
            except HTTPError as err:
                if err.code != http.client.CONFLICT:
                    print(TextIOWrapper(err, "ascii", "replace").read())
                    raise
                print(err, err.headers)
                # TODO: check content type
                charset = err.headers.get_content_charset()
                parser = ElementTree.XMLParser(encoding=charset)
                dump_tree(ElementTree.parse(err, parser).getroot())
                raise
        [values, edit] = parse_row(entry)
        self.view.item(self.item, values=values)
        self.edit_links[self.item] = edit
    
    def on_add_enter(self, event):
        with closing(self.send_atom("POST", self.post)) as request:
            xml = next(request)  # Start sending request body
            for [name, entry] in zip(self.name_list, self.add_entries):
                name = "gsx:" + name
                xml.startElement(name, xmlreader.AttributesImpl(dict()))
                xml.characters(entry.get())
                xml.endElement(name)
                xml.ignorableWhitespace("\n")
            [entry] = request  # Finish request and receive response
        item = self.add_entry(entry)
        self.view.selection_set((item,))
        self.view.see(item)
    
    def send_atom(self, method, url):
        request = urllib.request.Request(url, method=method)
        request.add_header(*self.auth)
        request.add_header("Accept", ", ".join(ATOM_TYPES))
        request.add_header("Content-Type",
            "application/atom+xml; charset=UTF-8")
        request.add_header("Transfer-Encoding", "chunked")
        print(method, url, end=" ", flush=True, file=sys.stderr)
        self.connection.start_request(request)
        encoder = ChunkEncoder(self.connection.get_writer())
        stream = TextIOWrapper(encoder, "utf-8", "xmlcharrefreplace",
            newline="\r\n")
        with stream:
            xml = XMLGenerator(stream, "UTF-8",
                short_empty_elements=True)
            xml.startDocument()
            xml.startElement("entry", xmlreader.AttributesImpl({
                "xmlns": ATOM_NS,
                "xmlns:gsx": GOOGLE_SHEETX_NS,
            }))
            yield xml
            xml.endElement("entry")
            xml.ignorableWhitespace("\n")
            xml.endDocument()
        encoder.write_eof()
        with self.connection.get_response() as response:
            print(response.status, response.reason,
                end="", flush=True, file=sys.stderr)
            type = response.msg.get_content_type()
            if type not in ATOM_TYPES:
                raise TypeError("Unexpected content type " + repr(type))
            charset = response.msg.get_content_charset()
            parser = ElementTree.XMLParser(encoding=charset)
            tree = ElementTree.parse(response, parser)
        print(file=sys.stderr)
        yield tree
    
    def get_feed(self, rel, projection=None, query=()):
        url = atom_link(self.worksheet, rel)
        if projection is not None:
            url = urljoin_path(url, projection)
        url = urllib.parse.urljoin(url, "?" + urllib.parse.urlencode(query))
        return self.atom_request(url=url, headers=(self.auth,))
    
    def add_entry(self, entry):
        [values, edit] = parse_row(entry)
        item = self.view.add(values=values)
        self.edit_links[item] = edit
        return item
    
    def atom_request(self, *, method="GET", url, headers=(), **args):
        all_headers = [self.auth]
        all_headers.extend(headers)
        print(method, url, end=" ", flush=True, file=sys.stderr)
        with http_request(urlopen=self.session.open, types=ATOM_TYPES,
                method=method, url=url, headers=all_headers,
                **args) as response:
            print(response.status, response.reason,
                end="", flush=True, file=sys.stderr)
            charset = response.info().get_content_charset()
            parser = ElementTree.XMLParser(encoding=charset)
            tree = ElementTree.parse(response, parser)
        print(file=sys.stderr)
        return tree

class Filter:
    def __init__(self, ui, column):
        self.ui = ui
        self.column = column
        self.window = tkinter.Toplevel(self.ui.tk)
        self.window.bind("<Return>", self.on_enter)
        self.window.bind("<KP_Enter>", self.on_enter)
        self.window.bind("<Escape>", self.on_escape)
        self.window.wm_title("Filter")
        self.entry = Entry(self.window)
        self.entry.pack(fill=tkinter.BOTH)
        self.entry.focus_set()
    
    def on_escape(self, event):
        self.window.destroy()
    
    def on_enter(self, event):
        filter = self.entry.get()
        attached = list()
        for item in sorted(self.ui.edit_links.keys()):
            if self.ui.view.set(item, self.column) == filter:
                attached.append(item)
        self.ui.view.set_children("", *attached)
        self.window.destroy()

def parse_login_response(headers, stream):
    charset = headers.get_content_charset("ascii")
    # TODO: limit size of response
    result = dict()
    for line in TextIOWrapper(stream, charset):
        line = line.rstrip("\r\n")
        [name, value] = line.split("=", 1)
        if name in result:
            raise ValueError(line)
        result[name] = value
    return result

def parse_row(entry):
    values = list()
    for child in entry.iter():
        if not child.tag.startswith("{" + GOOGLE_SHEETX_NS + "}"):
            continue
        values.append("".join(child.itertext()))
    return (values, atom_link(entry, "edit"))

def atom_link(root, rel):
    xpath = "{}link[@rel='{}'][@type][@href]".format(ATOM_PREFIX, rel)
    links = root.iterfind(xpath)
    [link] = (link for link in links if link.get("type") in ATOM_TYPES)
    return link.get("href")

def dump_tree(element, indent=""):
    namespaces = {
        "{" + ATOM_NS: "",
        "{" + OPEN_SEARCH_NS: "os:",
        "{" + GOOGLE_SHEET_NS: "gs:",
        "{" + GOOGLE_SHEETX_NS: "gsx:",
    }
    [ns, tag] = element.tag.rsplit("}", 1)
    attrib = sorted(element.attrib.items())
    attrib = "".join(" {}={!r}".format(*item) for item in attrib)
    print(indent + namespaces[ns] + tag + attrib)
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
    
    tk = tkinter.Tk()
    
    sys.stdin = rewrap(sys.stdin, newline="")
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

def paint():
    from fpdf import FPDF
    sys.stdin = rewrap(sys.stdin, newline="")
    reader = csv.reader(sys.stdin)
    # A4
    width = 0.5 ** (0.5 * (4 - 0.5)) / 1e-3
    height = 0.5 ** (0.5 * (4 + 0.5)) / 1e-3
    pdf = FPDF(orientation="L", unit="mm", format=(height, width))
    pdf.add_page()
    pdf.set_font("Times", size=9)
    next_y = 0
    for record in reader:
        y = next_y
        used = []
        ys = []
        for [i, data] in enumerate(record):
            data = data.strip().replace("•", "*").replace("–", "--").replace("\n", "  ")
            extent = pdf.get_string_width(data)
            if i > len(record) / 2:
                align = "R"
                space = (i + 1) / len(record) * width
                left = space - extent
                x = 0
                right = space
            else:
                align = "L"
                left = i / len(record) * width
                space = width - left
                x = left
                right = left + extent
            for [r, upto] in enumerate(used):
                if left >= upto:
                    y = ys[r]
                    break
            else:
                r = len(used)
                used.append(None)
                y = next_y
                ys.append(y)
            pdf.set_y(y)
            pdf.set_x(x)
            pdf.multi_cell(space, 9 / 72 * 25.4, data, align=align)
            used[r] = right
            next_y = max(next_y, pdf.get_y())
    pdf.output()

class ChunkEncoder(BufferedIOBase):
    def writable(self):
        return True
    
    def __init__(self, writer):
        self._writer = writer
    
    def write(self, b):
        with memoryview(b) as view:
            if not view.nbytes:
                return 0
            line = "{:X}\r\n".format(view.nbytes)
            self._writer.write(line.encode("ascii"))
            self._writer.write(b)
            self._writer.write(b"\r\n")
            return view.nbytes
    
    def write_eof(self):
        self._writer.write(b"0\r\n" b"\r\n")

def urljoin_path(base, *segments):
    segments = (urllib.parse.quote(segment, safe=()) for segment in segments)
    return urllib.parse.urljoin(base, "/".join(segments))

def valid_colour(widget, name, default):
    try:
        widget.winfo_rgb(name)
        return name
    except tkinter.TclError:
        return default

class AlnumOnlyMap(UnicodeMap):
    def map_char(self, char):
        if char.isalnum():
            return char
        else:
            return None

INHERIT = object()

def rewrap(stream,
        encoding=INHERIT, errors=INHERIT, newline=None,
        line_buffering=INHERIT, write_through=False):
    if encoding is INHERIT:
        encoding = stream.encoding
    if errors is INHERIT:
        errors = stream.errors
    if line_buffering is INHERIT:
        line_buffering = stream.line_buffering
    return TextIOWrapper(stream.detach(), encoding, errors,
        newline=newline, line_buffering=line_buffering,
        write_through=write_through)

if __name__ == "__main__":
    import clifunc
    clifunc.run()
