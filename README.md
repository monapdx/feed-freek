# FEED//FREAK

**Your corner of the internet.** A local RSS and Atom reader with a dark, neon interface. No account, no tracking, and no third-party Python packages.

## Start reading

Requires Python 3.10 or newer and a modern browser.

**Windows:** Extract the whole ZIP into a folder, then double-click `START.bat`. Keep the terminal open while you use the reader.

**macOS / Linux:** Open a terminal in the extracted folder and run:

```sh
python3 app.py
```

Your browser opens at http://127.0.0.1:8765. Close the terminal or press Ctrl+C to stop the server. If the port is occupied, run `python3 app.py --port 8766`. Use `--no-browser` to start without automatically opening a browser.

## Using the reader

- Subscribe with a **direct RSS or Atom URL**. Website homepage URLs are not automatically discovered.
- Refresh feeds manually to fetch stories. Failed feeds show their errors beside the subscription.
- Switch between Everything, Unread, Saved, or an individual feed.
- Search article titles and excerpts in the current view. At most 500 matching stories are shown.
- Sort by newest received (default), newest published, or oldest published.
- Open a preview to mark a story read. Save stories to revisit them later. Full articles open on their original sites.
- On smaller screens, use the Feeds menu. On phones, use Back to articles after reading a preview.
- Import/export subscriptions as OPML. Imports process at most 500 feeds per file.
- “Mark library read” affects the entire library, including articles outside your search. “Mark feed read” affects the selected feed.

## Data and updates

Subscriptions, excerpts, and reading history are stored in `reader.db` beside `app.py`. Close the app before backing up that file. Keep it when replacing the application files to upgrade. Existing databases from the earlier FEED//FREAK version are supported.

OPML backs up subscriptions only; use the database file to preserve reading history and saved stories. Feed URLs may contain private tokens: review exported OPML before sharing it.

The server binds to `127.0.0.1`, accessible on this computer. It makes network requests to the feeds you subscribe to. It is a personal local application, not a server intended for public hosting. GitHub Pages cannot run its Python backend.

## Development

- `app.py`: standard-library HTTP server, feed parser, SQLite storage.
- `index.html`: interface structure.
- `style.css`: responsive visual design.
- `app.js`: browser interactions.

Run the regression checks with `python3 -m unittest discover -s tests`. UI files are read on request: refresh the browser after editing them. Restart the server after editing Python.

Known limits: excerpts are plain text and capped at 1,200 characters; no automatic refresh, full-text fetching, folders, or cloud synchronization. Feed fetching is sequential, so large imports and refreshes take time. Some sites block automated requests.
