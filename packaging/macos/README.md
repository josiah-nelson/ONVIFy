# macOS Packaging

## launchd Service

```bash
# Install
sudo cp packaging/macos/com.onvify.server.plist /Library/LaunchDaemons/
sudo launchctl load /Library/LaunchDaemons/com.onvify.server.plist

# Check status
sudo launchctl list | grep onvify

# View logs
tail -f /opt/onvify/logs/onvify.log
```

## Apple Silicon Optimization

On Apple Silicon Macs, ONVIFy automatically uses:
- **MPS** (Metal Performance Shaders) for GPU-accelerated YOLO inference
- **CoreML** with Apple Neural Engine for 5-10x faster inference (when coremltools is installed)

Install CoreML support:
```bash
pip install -e ".[inference,coreml]"
```
