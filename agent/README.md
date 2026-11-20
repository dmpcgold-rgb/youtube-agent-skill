# YouTube Agent CLI (opt-in publishing)

This extends the original 11 Claude skills. The skills still create the content and draft metadata; the optional CLI adds a **local queue**, **OAuth channel read access**, and **approval-gated uploads**. It does not create or render finished video from a transcript. No upload occurs during prepare, list, approve, or channel.

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/dmpcgold-rgb/youtube-agent-skill.git
cd youtube-agent-skill
python3 -m pip install -r agent/requirements.txt
python3 -m unittest discover -s tests -v
```

For API use, create an OAuth **Desktop app** client in Google Cloud Console for a project with the YouTube Data API v3 enabled. Download its JSON to `client_secret.json` in this repository (ignored by Git). The browser consent flow runs locally and stores tokens under `.youtube-agent/token.json` (also ignored by Git). Use an account with channel permissions. Never commit or share these files. OAuth testing mode may require adding the account as a test user. Unverified apps may display a consent warning.

## Review-driven upload

```bash
python3 agent/yt_agent.py prepare /absolute/path/video.mp4 --title "My video" --description-file description.txt --privacy private --tag example
python3 agent/yt_agent.py list
# Inspect the draft, then type its exact job ID from the output:
python3 agent/yt_agent.py approve JOB_ID --confirm "APPROVE JOB_ID"
# This is the only action that transfers video bytes to YouTube:
python3 agent/yt_agent.py upload JOB_ID
```

Default visibility is **private**. To publish publicly, supply `--privacy public` at prepare time and explicitly approve that specific job. Changes to title, description, privacy, tags, or path after approval invalidate the approved digest. A second upload of a recorded successful job is blocked. There is no auto-publishing scheduler, and no command writes comments automatically.

For read-only account overview:

```bash
python3 agent/yt_agent.py channel
```

If you change OAuth scopes, an old cached token might not cover the new scope; delete the local token file and reauthorize. YouTube upload requests can consume significant API quota. Video uploads by unverified API projects may be restricted to private visibility by YouTube. The CLI cannot override YouTube policy restrictions.

## Workflow with the existing skills

1. `/yt-plan` prioritizes an idea.
2. `/yt-script`, `/yt-package` and `/yt-seo` prepare approved text.
3. `/yt-edit`, `/yt-shorts`, `/yt-chapters` generate production instructions. Assemble the finished video manually in an editor.
4. `prepare` registers the final exported video and reviewed metadata, without upload.
5. `approve` records explicit consent for this exact package; `upload` transmits it.
6. `channel`, `/yt-retention` and `/yt-audit` inform the next production cycle.

The original 11 skills are unchanged, including their requirement for manual review.

## Safety model and limits

- Approval covers metadata and the **file path**, a SHA-256 content hash of the entire video. Replacing the file at the same path after approval blocks uploading.
- Uploads are network operations and can succeed remotely even if the client times out before recording the video ID. Inspect YouTube Studio before retrying a failed upload.
- Channel access is OAuth and requires interactive owner authorization. There is no connection configured by cloning this repository.
- Generated descriptions, scripts and plans must be reviewed for accuracy and copyright.
