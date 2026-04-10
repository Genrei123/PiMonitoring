import 'package:flutter/material.dart';
import 'package:flutter_mjpeg/flutter_mjpeg.dart';

import 'stream_config.dart';

class CameraViewer extends StatefulWidget {
  final int camIndex;
  const CameraViewer({super.key, required this.camIndex});

  @override
  State<CameraViewer> createState() => _CameraViewerState();
}

class _CameraViewerState extends State<CameraViewer> {
  String _streamUrl = '';

  @override
  void initState() {
    super.initState();
    _rebuildUrl();
    StreamConfig.instance.baseUrl.addListener(_rebuildUrl);
  }

  void _rebuildUrl() {
    final base = StreamConfig.instance.baseUrl.value;
    setState(() {
      _streamUrl = '$base/cam/${widget.camIndex}/mjpeg';
    });
  }

  @override
  void dispose() {
    StreamConfig.instance.baseUrl.removeListener(_rebuildUrl);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final status = _streamUrl.isEmpty ? 'Connecting...' : 'Live';

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    'Camera ${widget.camIndex}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 16,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  status,
                  style: TextStyle(
                    color: _streamUrl.isEmpty ? Colors.orange : Colors.teal,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          AspectRatio(
            aspectRatio: 16 / 9,
            child: _streamUrl.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : Mjpeg(
                    stream: _streamUrl,
                    isLive: true,
                    fit: BoxFit.contain,
                    timeout: const Duration(seconds: 8),
                    loading: (context) => const Center(
                      child: CircularProgressIndicator(),
                    ),
                    error: (context, error, stack) => const Center(
                      child: Text('Waiting for stream...'),
                    ),
                  ),
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}
