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
        
        if input is None:
            input = rewrap(stdin, newline="")
        else:
            input = open(input, "rt", newline="")
        with input as input:
            input = csv.reader(input)
            columns = next(input)
            columns = (dict(heading=heading, width=10)
                for heading in columns)
            self.view = Tree(self.tk, tree=False, columns=columns)
            scroll(self.view)
            self.view.bind("<Button-3>", self.on_context)
            self.view.focus_set()
            
            self.items = list()
            for record in input:
                assert len(record) == len(columns)
                self.items.append(self.view.add(values=record))
        
        self.tk.mainloop()
    
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
