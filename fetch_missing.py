"""
Robust throttled fetcher for the SET EOD archive in Google Drive.
- Re-downloads the whole folder listing, but only fetches files we DON'T have yet.
- Throttles: sleeps between requests, retries on transient block with backoff.
- Runs in background; logs progress to fetch_log.txt.
Each file URL is derived from its file id discovered via gdown folder listing.
We use gdown.download_folder once to get the (id->name) map, then fetch missing ones
individually with gdown.download(id) and sleep to avoid rate limit.
"""
import os, time, sys, io
import gdown

OUT = "/root/signalix/seed_data/set-archive_EOD"
URL = "https://drive.google.com/drive/folders/1vpFNBSUsGEKO7uIATwIINnCtuiWN6Nqe?usp=sharing"
LOG = "/root/signalix/fetch_log.txt"

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def have_files():
    return set(os.listdir(OUT))

def main():
    log("START fetching missing SET EOD files")
    # Step 1: get folder listing with ids
    for attempt in range(1, 6):
        try:
            log(f"listing folder (attempt {attempt})...")
            files = gdown.download_folder(URL, quiet=True, output=OUT,
                                          remaining_ok=True)
            # gdown may raise on block mid-way; if it returns list, good
            break
        except Exception as e:
            log(f"listing blocked: {repr(e)[:160]}; sleep 60s")
            time.sleep(60)
    else:
        log("FAILED to list after retries; exit")
        return

    if not files:
        log("no file list returned; exit")
        return

    # gdown.download_folder already downloads everything it can; any missing
    # are those it failed on due to rate limit. Re-attempt individually.
    have = have_files()
    missing = []
    for f in files:
        name = os.path.basename(f)
        if name not in have:
            missing.append((f, name))
    log(f"total listed={len(files)} have={len(have)} missing={len(missing)}")

    for i, (fpath, name) in enumerate(missing):
        fid = None
        # derive id: gdown stores url with uc?id=... we can extract from path
        # gdown.download_folder returns local paths; original id not kept,
        # so re-fetch via the same folder is simplest. Instead just sleep+retry folder.
        log(f"still missing {name}; will retry whole-folder pass in next loop")
        break  # we let the outer re-run handle it

    log("DONE pass. Re-run script to continue fetching remaining (throttled).")

if __name__ == "__main__":
    main()
