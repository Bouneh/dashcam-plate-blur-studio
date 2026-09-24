# Contributing

Thanks for helping improve Plaque Studio. Bug reports, documentation fixes and pull requests are welcome.

## Before opening an issue

Search existing issues, then include your operating system, Docker or native setup, the command you ran, and the relevant error output. Do not attach private dashcam footage or model weights. A small synthetic video is ideal for reproducing a processing problem.

## Before opening a pull request

1. Explain the problem and the behavior your change adds or fixes.
2. Keep the English and French interface text in sync when changing UI copy.
3. Run the checks below, and describe how you manually verified a video-processing change.

```bash
python -m unittest discover -s tests -v
node --test tests/test_i18n.js
node --check web/app.js
node --check web/i18n.js
```

The web app is intentionally lightweight: a Python HTTP server, vanilla JavaScript and CSS, YOLOv8 inference, and FFmpeg encoding. The original batch scripts are kept for compatibility.
