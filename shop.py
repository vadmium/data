#! /usr/bin/env python3

import csv
from sys import stderr, stdout
from io import TextIOWrapper, BufferedIOBase
from net import PersistentConnectionHandler, http_request
import urllib.request
from xml.etree.ElementTree import TreeBuilder
from urllib.parse import urlsplit
from contextlib import ExitStack
from html.parser import HTMLParser
from streams import DelegateWriter
from shutil import copyfileobj
import os, os.path
import hashlib
from base64 import urlsafe_b64encode
from email.message import Message
import email.generator
from data import rewrap

class main:
    def __init__(self):
        with PersistentConnectionHandler(timeout=100) as handler:
            urlopen = urllib.request.build_opener(handler).open
            url = "https://au.rs-online.com/web/c/" \
                "connectors/pcb-connectors/pcb-pin-socket-strips/"
            print(end="GET {} ".format(url), flush=True, file=stderr)
            split = urlsplit(url)
            path = split.path.split("/")
            dir = os.path.join(split.scheme, split.netloc, *path[:-1])
            suffix = hashlib.md5()
            suffix.update(url.encode())
            suffix = urlsafe_b64encode(suffix.digest()[:6]).decode("ascii")
            if path[-1]:
                suffix = path[-1] + os.extsep + suffix
            suffix += os.extsep
            metadata = os.path.join(dir, suffix + "mime")
            with ExitStack() as cleanup:
                try:
                    metadata = open(metadata, "rb")
                except FileNotFoundError:
                    types = ("text/html",)
                    os.makedirs(dir, exist_ok=True)
                    suffix += "html"
                    cache = open(os.path.join(dir, suffix), "xb")
                    cleanup.enter_context(cache)
                    with open(metadata, "xb") as metadata:
                        response = http_request(url, types, urlopen=urlopen)
                        cleanup.enter_context(response)
                        print(response.status, response.reason,
                            flush=True, file=stderr)
                        msg = Message()
                        msg.add_header("Content-Type",
                            "message/external-body; access-type=local-file")
                        msg.set_param("name", suffix)
                        msg.attach(response.info())
                        metadata = email.generator.BytesGenerator(metadata,
                            mangle_from_=False, maxheaderlen=0)
                        metadata.flatten(msg)
                    msg = response.info()
                    response = TeeReader(response, cache.write)
                else:
                    with metadata:
                        msg = email.message_from_binary_file(metadata)
                    cache = os.path.join(dir, msg.get_param("name"))
                    [msg] = msg.get_payload()
                    response = cleanup.enter_context(open(cache, "rb"))
                    print("(cached)", flush=True, file=stderr)
                charset = msg.get_content_charset()
                response = TextIOWrapper(response, charset)
                cleanup.enter_context(response)
                parser = HtmlTreeParser()
                print(end="Parsing HTML ", flush=True, file=stderr)
                # TODO: limit data
                copyfileobj(response, DelegateWriter(parser.feed))
                print("done", flush=True, file=stderr)
            response = parser.close()
            
            [counter] = response.iterfind(".//*[@class='mpcCounter']")
            counter = "".join(counter.itertext())
            
            with rewrap(stdout, newline="") as out:
                out = csv.writer(out)
                header = None
                for elem in response.iterfind(".//table[@class]"):
                    if "srtnTblHeader" in elem.get("class").split():
                        assert header is None
                        header = elem
                header = header.find(".//tr")
                header = ("".join(cell.itertext()).strip()
                    for cell in header.iter("td"))
                
                out_header = ["href", "prodDesc"]
                out_header.append(next(header))
                out_header.extend(("packaging", "qty"))
                part_header = list()
                cell = next(header)
                assert cell == "Part Details"
                header = list(header)
                
                [table] = response.iterfind(".//table[@class='srtnListTbl']")
                for [i, row] in enumerate(table.iterfind(".//tr")):
                    row = row.iterfind(".//td")
                    cell = next(row)
                    
                    [desc] = cell.iterfind(".//a[@class='tnProdDesc']")
                    out_row = [desc.get("href")]
                    out_row.append("".join(desc.itertext()).strip())
                    
                    pricing = None
                    for elem in cell.iterfind(".//span[1][@class]/.."):
                        if "price" in elem[0].get("class", "").split():
                            assert pricing is None
                            pricing = elem
                    pricing = iter(pricing)
                    out_row.append("".join(next(pricing).itertext()))
                    pricing = "".join(t
                        for elem in pricing for t in elem.itertext())
                    out_row.append(pricing)
                    
                    [qty] = cell.iterfind(".//*[@class='qty']//input")
                    qty = int(qty.get("value"))
                    out_row.append(qty)
                    if qty == 1:
                        expected = ("Each", "1 ")
                    else:
                        expected = "Each (In a Pack of {})".format(qty)
                    assert pricing.startswith(expected), (qty, pricing)
                    
                    cell = next(row)
                    labels = list()
                    for detail in cell.iterfind(".//li"):
                        labels.append("".join(detail[0].itertext()))
                        text = "".join(t
                            for elem in detail[1:] for t in elem.itertext())
                        out_row.append(text.strip())
                    
                    out_row.extend("".join(cell.itertext()).strip()
                        for cell in row)
                    
                    if i:
                        assert labels == part_header
                    else:
                        part_header = labels
                        out.writerow(out_header + part_header + header)
                    out.writerow(out_row)

class HtmlTreeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._builder = TreeBuilder()
    
    def close(self):
        super().close()
        return self._builder.close()
    
    def handle_starttag(self, tag, attrs):
        self._builder.start(tag, dict(attrs))
    def handle_endtag(self, *pos, **kw):
        self._builder.end(*pos, **kw)
    def handle_data(self, *pos, **kw):
        self._builder.data(*pos, **kw)

def dump_tree(tree, _indent=""):
    if not isinstance(stdout, TextIOWrapper):
        _dump_element(stdout, html, "")
        return
    with rewrap(stdout.buffer, errors="backslashreplace") as out:
        _dump_element(out, tree, "")

def _dump_element(out, element, _indent=""):
    attrib = sorted(element.attrib.items())
    attrib = "".join(" {}={!r}".format(*item) for item in attrib)
    print(_indent + element.tag + attrib, file=out)
    if element.text:
        print(_indent + "  " + repr(element.text), file=out)
    for child in element:
        _dump_element(out, child, _indent + "  ")
    if element.tail:
        print(_indent + repr(element.tail), file=out)

class TeeReader(BufferedIOBase):
    def readable(self):
        return True
    
    def __init__(self, source, *write):
        self._source = source
        self._write = write
    
    def read(self, *pos, **kw):
        result = self._source.read(*pos, **kw)
        self._call_write(result)
        return result
    def read1(self, *pos, **kw):
        result = self._source.read1(*pos, **kw)
        self._call_write(result)
        return result
    
    def readinto(self, b):
        n = self._readinto(b)
        with memoryview(b) as view, view.cast("B") as bytes:
            self._call_write(bytes[:n])
        return n
    def readinto1(self, b):
        n = self._readinto(b)
        with memoryview(b) as view, view.cast("B") as bytes:
            self._call_write(bytes[:n])
        return n
    
    def _call_write(self, b):
        for write in self._write:
            write(b)

if __name__ == "__main__":
    import clifunc
    clifunc.run()
