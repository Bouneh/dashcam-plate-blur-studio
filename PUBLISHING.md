# Repository presentation

## GitHub details

- **Repository:** [Bouneh/dashcam-plate-blur-studio](https://github.com/Bouneh/dashcam-plate-blur-studio)
- **About:** `Local web app to automatically blur license plates in dashcam videos. YOLOv8 + FFmpeg, Docker Compose, live preview, English/French UI.`
- **Topics:** `dashcam`, `license-plate-blur`, `video-anonymization`, `privacy`, `yolov8`, `ffmpeg`, `docker`, `computer-vision`.
- **Website:** leave blank until a demo or documentation site exists.
- **Social preview:** use a 1280 × 640 PNG or JPG based on the colors and artwork in `media/plaquestudio-banner.svg`. GitHub recommends this size and a file under 1 MB; see [social preview guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview).

## Release checklist

1. Run the Python and JavaScript checks in [README.md](README.md).
2. Check that a clean clone starts with `docker compose up --build -d` and that the model download succeeds.
3. Verify the English and French interface and one processed MP4 with audio.
4. Review `git status --short` before publishing; local videos, job data, model weights and virtual environments should remain excluded.
5. Add release notes and a tag for user-facing milestones.

The project builds on [Varun Gupta's Dashcam Anonymizer](https://github.com/varungupta31/dashcam_anonymizer). Keep its license notice and attribution when releasing changes.
