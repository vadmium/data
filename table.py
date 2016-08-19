#! /usr/bin/env python3

import csv
from sys import stdin
import tkinter
from tkwrap import Tree, scroll
from tkinter.ttk import Frame, Entry
from data import rewrap

class main:
    def __init__(self, input=None):
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
            columns = next(input)
            columns = (dict(heading=heading, width=10)
                for heading in columns)
            self.view = Tree(view_frame, tree=False, columns=columns)
            scroll(self.view)
            self.view.bind("<ButtonPress-1>", self.on_press)
            self.view.bind("<B1-Motion>", self.on_drag)
            self.view.bind("<ButtonRelease-1>", self.on_release)
            self.view.bind("<Button-3>", self.on_context)
            self.view.focus_set()
            
            self.items = list()
            for record in input:
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
                return self.view.set(item, column)
            items = sorted(self.view.get_children(), key=key)
            self.view.set_children("", *items)
    
    def get_click(self, event):
        region = self.view.identify_region(event.x, event.y)
        click = [region]
        if region in {"heading", "cell"}:
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

if __name__ == "__main__":
    import clifunc
    clifunc.run()
