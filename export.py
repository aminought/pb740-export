import base64
import json
import sqlite3
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

class Highlight:
    def __init__(self, text: str, snapshot: bytes = None):
        self.text = text
        self.snapshot = snapshot


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


def get_item_ids(con: sqlite3.Connection, book_oid: int) -> List[int]:
    sql = '''
        SELECT t.ItemID
        FROM Items i
        JOIN Tags t ON t.ItemID = i.OID
        JOIN TagNames tn ON tn.OID = t.TagID    
        WHERE i.ParentID = ?
        AND tn.TagName = 'bm.type'
        AND t.Val = 'highlight'
    '''
    cur = con.execute(sql, (book_oid,))
    item_ids = [row[0] for row in cur]
    return item_ids


def get_highlights(con: sqlite3.Connection,
                   book_oid: int) -> List[Highlight]:
    highlights = []
    item_ids = get_item_ids(con, book_oid)

    for item_id in item_ids:
        sql = '''
            SELECT Val
            FROM Tags t
            JOIN TagNames tn ON tn.OID = t.TagID
            WHERE t.ItemId = ?
            AND tn.TagName = 'bm.quotation'
        '''
        cur = con.execute(sql, (item_id,))
        row = cur.fetchone()
        if row is not None:
            val = row[0]
            o = json.loads(val)
            text = o['text']
            if text == 'Snapshot':
                sql = '''
                    SELECT Val
                    FROM Tags t
                    JOIN TagNames tn ON tn.OID = t.TagID
                    WHERE t.ItemId = ?
                    AND tn.TagName = 'bm.image'
                '''
                cur = con.execute(sql, (item_id,))
                row = cur.fetchone()
                if row is not None:
                    highlight = Highlight(None, row[0])
                    highlights.append(highlight)
            else:
                highlight = Highlight(o['text'])
                highlights.append(highlight)

    return highlights


def export(books: List[Book], path: str):
    doc = dominate.document(title='PocketBook 740')

    with doc:
        h1('Hightlights')
        for book in books:
            with div(id='book'):
                h2(book.title)
                with ol():
                    for highlight in book.highlights:
                        if highlight.text is not None:
                            li(highlight.text)
                        else:
                            image = highlight.snapshot
                            b64 = base64.b64encode(image).decode('utf8')
                            li(raw(f'<img src="data:image/jpeg;base64,{b64}"/>'))

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

    con.close()

    export(books, 'export.html')


if __name__ == '__main__':
    main()
