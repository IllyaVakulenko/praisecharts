## PraiseCharts Sheet Downloader

A small, focused CLI tool that downloads sheet previews from PraiseCharts song detail pages, organizes images by song, arrangement, and instrument, and automatically assembles per‑instrument PDF files.

The tool supports:
- Single URL mode (interactive conflict handling: [O]verwrite, [N]umber, [S]kip, [Q]uit)
- Batch mode from a .txt file with URLs and interactive conflict resolution

Outputs are stored under `charts/` in a predictable structure. Colorful, human‑friendly console messages guide you through the process and finish with a clear summary.

This README has two parts:
- For Users: Installation, prerequisites, how to run, what you’ll see, and how to resolve conflicts
- For Contributors: Project structure, local dev setup, contribution guidelines


### Table of Contents
- [For Users](#for-users)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Quick Start](#quick-start)
  - [Usage](#usage)
    - [Single URL](#single-url)
    - [Batch from File](#batch-from-file)
    - [CLI Help](#cli-help)
  - [What Gets Downloaded](#what-gets-downloaded)
  - [Directory Layout](#directory-layout)
  - [Interactive Prompts Explained](#interactive-prompts-explained)
  - [Understanding the Summary](#understanding-the-summary)
  - [Troubleshooting](#troubleshooting)
- [For Contributors](#for-contributors)
  - [Project Structure](#project-structure)
  - [Local Development](#local-development)
  - [Code Overview](#code-overview)
  - [Contribution Guidelines](#contribution-guidelines)
  - [Ideas and Improvements](#ideas-and-improvements)


## For Users

### Prerequisites
- Python 3.10 or newer
- Firefox browser installed
- Geckodriver installed and available on your PATH
  - Windows (Scoop): `scoop install geckodriver`
  - Windows (Chocolatey): `choco install geckodriver`
  - Windows (Winget): `winget install Mozilla.GeckoDriver`
  - macOS (Homebrew): `brew install geckodriver`
  - Linux (Debian/Ubuntu): `sudo apt-get install firefox-esr` and install a matching `geckodriver` from Mozilla releases

Note: Selenium requires Firefox and Geckodriver versions that are compatible with each other. You can check with:

```sh
geckodriver --version
firefox --version
```


### Installation
It’s best to use a virtual environment to keep dependencies isolated.

```sh
python -m venv .venv
.\u200b.\venv\Scripts\activate    # Windows PowerShell
# source .venv/bin/activate      # macOS/Linux

pip install -r requirements.txt
```


### Quick Start
- Single URL:

```sh
python main.py --url https://www.praisecharts.com/songs/details/70645/o-holy-night-sheet-music/orchestration
```

- Batch from file (one URL per line):

```sh
python main.py --file temp/links.txt
```

The first time you run it, Firefox will open while the tool automatically navigates and downloads preview images. PDFs will be created per instrument once images are saved.


### Usage

#### Single URL
You can pass a URL either positionally or via `--url`:

```sh
python main.py https://www.praisecharts.com/songs/details/70645/o-holy-night-sheet-music/orchestration
# or
python main.py --url https://www.praisecharts.com/songs/details/70645/o-holy-night-sheet-music/orchestration
```

If the target arrangement folder already exists, you’ll be prompted:

```
Path 'charts/o-holy-night/orchestration' exists. [O]verwrite, [N]umber, [S]kip, [Q]uit?
```

Enter `O`, `N`, `S`, or `Q` (case‑insensitive). See details in [Interactive Prompts Explained](#interactive-prompts-explained).


#### Batch from File
Provide a `.txt` file containing one URL per line. Blank lines and lines starting with `#` are ignored. Only PraiseCharts “song details” URLs are accepted (must contain `/songs/details/`). Example `temp/links.txt`:

```text
https://www.praisecharts.com/songs/details/70645/o-holy-night-sheet-music/orchestration
https://www.praisecharts.com/songs/details/70645/o-holy-night-sheet-music/stage-chart
https://www.praisecharts.com/songs/details/70645/o-holy-night-sheet-music/chords
# A comment line below is ignored
https://www.praisecharts.com/songs/details/87415/what-an-awesome-god-sheet-music/orchestration
```

Run:

```sh
python main.py --file temp/links.txt
```

If any target arrangement folders already exist, you’ll get a “Conflict Resolution” section listing them with numbers. You can choose which ones to overwrite and which ones to “add number” (rename), or skip the rest by pressing Enter. Details in [Interactive Prompts Explained](#interactive-prompts-explained).


#### CLI Help

```sh
python main.py --help
```

Options you’ll see:
- `--url URL` or positional `URL`: download a single arrangement
- `--file PATH`: process many URLs from a `.txt` file
- `--debug`: enable verbose logging (useful for troubleshooting)


### What Gets Downloaded
- The tool navigates a PraiseCharts song details page and collects preview images for the current arrangement.
- Images are grouped by instrument (instrument name is parsed from the image filename).
- For each instrument folder, the images are sorted by page number (e.g., `_001.png`, `_002.png` …) and combined into a single PDF `instrument.pdf` placed in the arrangement folder.
- If a PDF already exists, it won’t be recreated.


### Directory Layout
Given a URL like `https://www.praisecharts.com/songs/details/70645/o-holy-night-sheet-music/orchestration`, files are saved under:

```
charts/
  o-holy-night/
    orchestration/
      Flute/
        o_holy_night_Flute_All_001.png
        o_holy_night_Flute_All_002.png
        ...
      Trumpet/
        o_holy_night_Trumpet_B_001.png
        ...
      Flute.pdf
      Trumpet.pdf
```

Song and arrangement names come from the URL. The instrument name comes from each image filename.


### Interactive Prompts Explained

Conflicts occur when a target arrangement directory already exists. The tool offers the following choices:

- [O]verwrite: Delete the existing arrangement directory and re‑download into the same path.
- [N]umber: Keep the existing directory and save the new download into the next available numbered folder by appending `_<n>` — e.g., `charts/o-holy-night/orchestration_1`, `orchestration_2`, etc.
- [S]kip: Do not download for this URL.
- [Q]uit: Abort the program immediately.

Notes:
- Inputs are case‑insensitive; only the first character is used.
- In single‑URL mode, entering anything other than `O`, `N`, or `Q` is treated as Skip.
- In batch mode, conflict resolution happens in two passes:
  1) You’re asked which conflicted items to Overwrite (enter indices like `1 3 5`, type `all` for all, or press Enter to skip this action)
  2) You’re asked which remaining conflicted items to Number
  Any conflicts not selected in those two steps are skipped.


### Understanding the Summary
At the end, a summary is printed:

```
New downloads: X
Overwritten: Y
Renamed: Z
Skipped: K
Errors: E
Work complete.
```

- New downloads: Arrangements that did not previously exist
- Overwritten: Conflicts you chose to overwrite
- Renamed: Conflicts you chose to “add number” (saved to `_1`, `_2`, ...)
- Skipped: Conflicts you left unselected (or chose Skip), plus any invalid URLs
- Errors: Tasks that failed due to network, filesystem, or browser automation issues


### Troubleshooting
- “Error: Required libraries are not installed.”
  - Run: `pip install -r requirements.txt`

- “Browser automation failed … Ensure Firefox and geckodriver are installed …”
  - Install Firefox and Geckodriver; ensure both are on PATH and versions are compatible.
  - Verify with `geckodriver --version` and `firefox --version`.

- Nothing downloads for a URL
  - Only PraiseCharts song details URLs are supported (must contain `/songs/details/`). Other pages are rejected.
  - Some URLs that redirect to the domain root are treated as invalid.

- PDFs not created
  - PDFs are created only when at least one PNG was saved for an instrument.
  - Existing PDFs are not overwritten.

- Run without opening browser (headless)
  - Advanced users can open `main.py` and uncomment the headless flag for Firefox options:
    - Look for `# options.add_argument("--headless")` and remove the leading `#`.

- Windows console colors look odd
  - Color output is handled by `colorama`; ensure your terminal supports ANSI colors (PowerShell usually does).

- Enable more diagnostics
  - Add `--debug` to print more detailed logs.


## For Contributors

### Project Structure
- `main.py`: CLI entrypoint and the complete implementation
- `charts/`: Default output directory for downloads
- `temp/links.txt`: Example input list for batch mode
- `requirements.txt`: Python dependency pins


### Local Development
1) Create and activate a virtual environment

```sh
python -m venv .venv
..\venv\Scripts\activate    # Windows PowerShell
# source .venv/bin/activate      # macOS/Linux
```

2) Install dependencies

```sh
pip install -r requirements.txt
```

3) Run in debug mode during development

```sh
python main.py --debug --url https://www.praisecharts.com/songs/details/70645/o-holy-night-sheet-music/orchestration
```

4) Formatting & linting
- The project does not currently enforce a formatter or linter. Please keep code clear, typed, and readable. Prefer early returns and descriptive names.


### Code Overview
High‑level flow in `main.py`:
- URL handling: normalization and validation to accept only PraiseCharts song details URLs
- Single vs batch: `--url`/positional vs `--file` mode (batch reads `.txt`, ignores comments and blanks)
- Conflict handling:
  - Single URL: [O]/[N]/[S]/[Q]
  - Batch: two prompts to select indices to Overwrite and Number; unselected conflicts are skipped
- Browser automation: Selenium + Firefox navigates the page and iterates preview images
- Downloading: images saved by instrument; content‑type checked for images; robust error handling
- PDF assembly: per‑instrument PDFs created with Pillow, preserving page order by numeric suffix


### Contribution Guidelines
- Fork the repository and create a feature branch from `main`
- Keep changes focused and small; write clear commit messages
- Test both single URL and batch modes, including conflict scenarios
- Update this README if your change affects usage or outputs
- Open a Pull Request with a description, screenshots (if relevant), and notes on testing


### Ideas and Improvements
- Optional headless mode exposed via CLI flag (default off)
- Add retries/backoff for flaky network calls
- Add unit tests for URL parsing, conflict resolution, and PDF assembly
- Configurable output directory via CLI
- Structured logging and a `--quiet` mode


---

Legal & Ethics: Use this tool responsibly and in accordance with PraiseCharts’ terms of service and applicable copyright laws. This tool is intended for personal, lawful use only.


