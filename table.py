#! /usr/bin/env python3

import csv
from sys import stdin
import tkinter
from tkwrap import Tree, scroll
from tkinter.ttk import Frame, Entry
from data import rewrap
from types import SimpleNamespace
import math

class main:
    def __init__(self, input=None, *, field=()):
        self.tk = tkinter.Tk()
        self.entry = Entry(self.tk)
        self.entry.pack(fill=tkinter.BOTH, side=tkinter.TOP)
        view_frame = Frame(self.tk)
        view_frame.pack(fill=tkinter.BOTH, side=tkinter.BOTTOM, expand=True)
        
        if input is None:
            input = rewrap(stdin, newline="")
        else:
            input = open(input, "rt", newline="")
        with input as input:
            self.tk.wm_title(input.name)
            input = csv.reader(input)
            headings = next(input)
            columns = list()
            for heading in headings:
                columns.append(dict(heading=heading, width=10))
            for heading in field:
                [heading, _] = heading.split("=", 1)
                columns.append(dict(heading=heading, width=10))
            self.view = Tree(view_frame, tree=False, columns=columns)
            scroll(self.view)
            self.view.bind("<ButtonPress-1>", self.on_press)
            self.view.bind("<B1-Motion>", self.on_drag)
            self.view.bind("<ButtonRelease-1>", self.on_release)
            self.view.bind("<Double-Button-1>", self.on_doubleclick)
            self.view.bind("<ButtonPress-3>", self.on_context)
            self.view.focus_set()
            
            self.items = list()
            for record in input:
                row = SimpleNamespace()
                for [heading, value] in zip(headings, record):
                    num = value
                    if num.startswith("$"):
                        num = num[1:]
                    try:
                        value = float(num)
                    except ValueError:
                        pass
                    setattr(row, heading.replace(" ", "_"), value)
                env = dict(row=row, math=math)
                for expr in field:
                    [_, expr] = expr.split("=", 1)
                    record.append(eval(expr, env))
                self.items.append(self.view.add(values=record))
        
        self.tk.mainloop()
    
    def on_press(self, event):
        self.click = self.get_click(event)
    def on_drag(self, event):
        self.click = [None]
    def on_release(self, event):
        if self.get_click(event) != self.click:
            return
        [region, *click] = self.click
        if region == "cell":
            [column, item] = click
            self.entry.delete(0, tkinter.END)
            self.entry.insert(0, self.view.set(item, column))
            self.entry.selection_range(0, tkinter.END)
            self.column = int(column.lstrip("#")) - 1
            self.entry.focus_set()
        if region == "heading":
            [column] = click
            def key(item):
                return alnum_key(self.view.set(item, column))
            items = sorted(self.view.get_children(), key=key)
            self.view.set_children("", *items)
    
    def on_doubleclick(self, event):
        [region, *click] = self.click
        if region == "separator":
            [column] = click
            width = max((self.view.min_width(item, column)
                for item in self.view.get_children()), default=0)
            self.view.column(column, width=width)
    
    def get_click(self, event):
        region = self.view.identify_region(event.x, event.y)
        click = [region]
        if region in {"heading", "separator", "cell"}:
            click.append(self.view.identify_column(event.x))
            if region == "cell":
                click.append(self.view.identify_row(event.y))
        return click
    
    def on_context(self, event):
        column = self.view.identify_column(event.x)
        if not column:
            return
        Filter(self, column)

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
        for item in sorted(self.ui.items):
            if self.ui.view.set(item, self.column) == filter:
                attached.append(item)
        self.ui.view.set_children("", *attached)
        self.window.destroy()

def alnum_key(value):
    '''
    >>> alnum_key("2") < alnum_key("10")
    True
    >>> alnum_key("2") < alnum_key("1,000")
    True
    >>> alnum_key(".9x") < alnum_key("1x") < alnum_key("1.1x")
    True
    >>> alnum_key("1.02") < alnum_key("1.1")
    True
    >>> alnum_key("1 a") < alnum_key("1b") < alnum_key("1 c")
    True
    '''
    numbers = list()
    i = 0
    while i < len(value):
        if value[i].isdecimal() or value[i] == ".":
            start = i
            while value[i:i + 1] == "," or value[i:i + 1].isdecimal():
                i += 1
            whole = value[start:i].translate(_DROP_COMMAS)
            start = i
            if value[i:i + 1] == ".":
                while True:
                    i += 1
                    if not value[i:i + 1].isdecimal():
                        break
            if whole:
                whole = int(whole)
            else:
                whole = 0
            numbers.append(("0", whole, value[start:i]))
            while value[i:i + 1].isspace():
                i += 1
        else:
            numbers.append((value[i],))
            i += 1
    return (numbers, value)

_DROP_COMMAS = str.maketrans({",": ""})

if __name__ == "__main__":
    import clifunc
    clifunc.run()
