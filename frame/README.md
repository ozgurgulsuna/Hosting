# Frame inbox

Put a photo in `frame/inbox/` and it becomes the picture on the Kindle frame. No PC needed.

GitHub runs `frame.py` (a fixed script, no AI): turns landscape photos upright, crops to 600×800,
tunes the tones for E Ink, reduces to 16 greys, and saves it as `/works.bmp`
(https://www.ozgurgulsuna.com/works.bmp). The frame shows it at its next wake (every 2–4 h).
The photo is then removed from `inbox/`, a preview goes to `previews/`, and a line to `history.md`.

**This repo is public:** uploaded photos stay readable in its history, at full size,
with whatever location data the phone put in them.

## From the phone
1. Open github.com/ozgurgulsuna/Hosting/tree/master/frame/inbox in the phone's browser (signed in).
2. **Add file → Upload files**, pick the photo, **Commit changes**.
3. A few minutes later the picture is online (**Actions** tab: green tick).

## Options: words in the file name
Rename the photo before uploading, e.g. `IMG_7900 left.jpg`.

| Word | Effect |
|---|---|
| `left` / `top` | crop from the left (top) end |
| `right` / `bottom` | crop from the right (bottom) end |
| `at30` | crop position 30 % (0 = left, 100 = right); default is the centre |
| `fit` | whole photo, white bars instead of cropping |
| `noturn` | landscape: crop a tall piece instead of turning the photo |
| `light` / `dark` | lighter or darker mid-greys |
| `paper` | drawing on paper: paper becomes clean white |

Several photos at once: only the newest is published, all are removed from `inbox/`.

`frame.py` is a copy of `frame-ink/scripts/frame.py`; copy it again after changing it there.
