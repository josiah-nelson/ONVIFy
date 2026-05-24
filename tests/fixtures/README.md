# Test Fixtures

Short (2-5 second) MP4 video samples used for deterministic inference pipeline tests.

## Expected Fixtures

| File | Content | Purpose |
|------|---------|---------|
| `person_walking.mp4` | Single person walking across frame | Verify person detection |
| `vehicle_passing.mp4` | Vehicle driving through frame | Verify vehicle detection |
| `static_scene.mp4` | Static scene with no motion | Verify motion gate blocks inference |
| `multi_object.mp4` | Multiple detectable objects | Verify multi-object detection |

## Requirements

- Each fixture must be under 5 MB
- CC0/public-domain or self-recorded (no copyrighted content)
- Resolution: 640x480 or 1280x720
- Codec: H.264 baseline profile for maximum compatibility
- Tests assert deterministic detection results against known frame contents

## Adding Fixtures

When adding a new fixture:
1. Record or source the video under a permissive license
2. Document its provenance in this file
3. Keep the file small (trim to the shortest clip that demonstrates the scenario)
4. Add corresponding test assertions in `tests/unit/` or `tests/integration/`
