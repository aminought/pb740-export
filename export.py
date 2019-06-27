import base64
import json
import sqlite3
import urllib.parse as urlparse
from datetime import datetime
from typing import List

import click
import dominate
from dominate.tags import *
from dominate.util import raw


class Book:
    def __init__(self, oid: int, title: str, authors: str):
        self.oid = oid
        self.title = title
        self.authors = authors
        self.file_name = None
        self.notes = []
        self.bookmarks = []
        self.highlights = []

    def render(self):
        if len(self.highlights) == 0 \
                and len(self.notes) == 0 \
                and len(self.bookmarks) == 0:
            return

        with div():
            h2(self.title)
            if self.authors is not None:
                p(f'Authors: {self.authors}')
            p(f'File: {self.file_name}')

            if len(self.bookmarks) > 0:
                h3('Bookmarks')
                with ol():
                    for bookmark in self.bookmarks:
                        with li():
                            bookmark.render()

            if len(self.highlights) > 0:
                h3('Highlights')
                with ol():
                    for highlight in self.highlights:
                        with li():
                            highlight.render()

            if len(self.notes) > 0:
                h3('Notes')
                with ol():
                    for note in self.notes:
                        with li():
                            note.render()


class Highlight:
    def __init__(self, text: str, snapshot: bytes = None):
        self.text = text
        self.snapshot = snapshot

    def render(self):
        with div():
            p(self.text)
            if self.snapshot is not None:
                image = self.snapshot
                b64 = base64.b64encode(image).decode('utf8')
                raw(f'<img src="data:image/jpeg;base64,{b64}"/>')


class Note:
    def __init__(self, quotation: str, note: str):
        self.quotation = quotation
        self.note = note

    def render(self):
        with div():
            p(self.note)
            blockquote(p(self.quotation))


class Bookmark:
    def __init__(self, page: int, text: str, created: datetime):
        self.page = page
        self.text = text
        self.created = created

    def render(self):
        with div():
            p(f'Page: {self.page}')
            p(f'Text: {self.text}')
            p(f'Created: {self.created}')


def get_books(con: sqlite3.Connection) -> List[Book]:
    books = []
    sql = 'SELECT * FROM Books'
    cur = con.execute(sql)
    for row in cur:
        book = Book(row[0], row[1], row[2])
        books.append(book)
    return books


def get_file_name(con: sqlite3.Connection, book_oid: int) -> str:
    sql = 'SELECT Name FROM Files WHERE BookID=?'
    cur = con.execute(sql, (book_oid,))
    row = cur.fetchone()
    if row is None:
        return None
    return row[0]


def select_items(con: sqlite3.Connection,
                 book_oid: int,
                 type_val: str) -> List[int]:
    sql = '''
        SELECT t.ItemID
        FROM Items i
        JOIN Tags t ON t.ItemID = i.OID
        JOIN TagNames tn ON tn.OID = t.TagID    
        WHERE i.ParentID = ?
        AND i.State = 0
        AND tn.TagName = 'bm.type'
        AND t.Val = ?
    '''
    cur = con.execute(sql, (book_oid, type_val))
    item_ids = [row[0] for row in cur]
    return item_ids


def select_quotation(con: sqlite3.Connection, item_id: int) -> str:
    sql = '''
        SELECT Val
        FROM Tags t
        JOIN TagNames tn ON tn.OID = t.TagID
        WHERE t.ItemId = ?
        AND tn.TagName = 'bm.quotation'
    '''
    cur = con.execute(sql, (item_id,))
    row = cur.fetchone()

    if row is None:
        return None

    val = row[0]
    o = json.loads(val)
    return o['text']


def select_tag_value(con: sqlite3.Connection, item_id: int, tag: str) -> str:
    sql = '''
        SELECT Val
        FROM Tags t
        JOIN TagNames tn ON tn.OID = t.TagID
        WHERE t.ItemId = ?
        AND tn.TagName = ?
    '''
    cur = con.execute(sql, (item_id, tag))
    row = cur.fetchone()

    if row is None:
        return None

    return row[0]


def get_highlights(con: sqlite3.Connection,
                   book_oid: int) -> List[Highlight]:
    highlights = []
    item_ids = select_items(con, book_oid, 'highlight')
    for item_id in item_ids:
        text = select_quotation(con, item_id)
        snapshot = select_tag_value(con, item_id, 'bm.image')
        highlight = Highlight(text, snapshot)
        highlights.append(highlight)
    return highlights


def get_notes(con: sqlite3.Connection,
              book_oid: int) -> List[Note]:
    notes = []
    item_ids = select_items(con, book_oid, 'note')
    for item_id in item_ids:
        quotation = select_quotation(con, item_id)
        val = select_tag_value(con, item_id, 'bm.note')
        o = json.loads(val)
        note = o['text']
        note = Note(quotation, note)
        notes.append(note)
    return notes


def get_bookmarks(con: sqlite3.Connection,
                  book_oid: int) -> List[Bookmark]:
    bookmarks = []

    item_ids = select_items(con, book_oid, 'bookmark')

    for item_id in item_ids:
        text = select_quotation(con, item_id)
        val = select_tag_value(con, item_id, 'bm.book_mark')
        o = json.loads(val)
        created = datetime.fromtimestamp(o['created'])
        anchor = o['anchor']
        parsed = urlparse.urlparse(anchor)
        query = urlparse.parse_qs(parsed.query)
        page = int(query['page'][0])
        bookmark = Bookmark(page, text, created)
        bookmarks.append(bookmark)
    return bookmarks


def export(books: List[Book], path: str):
    doc = dominate.document(title='PocketBook 740 export')

    with doc:
        for book in books:
            book.render()

    with open(path, 'w') as f:
        f.write(doc.render())


@click.command()
@click.argument('path', type=click.Path(exists=True))
def main(path):
    con = sqlite3.connect(path)
    books = get_books(con)

    for book in books:
        book.file_name = get_file_name(con, book.oid)
        book.highlights = get_highlights(con, book.oid)
        book.notes = get_notes(con, book.oid)
        book.bookmarks = get_bookmarks(con, book.oid)

    con.close()

    export(books, 'export.html')


if __name__ == '__main__':
    main()
