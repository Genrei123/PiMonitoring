import 'package:flutter/material.dart';

import 'camera_viewer.dart';
import 'stream_config.dart';

const int kCameraCount = 1;

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await StreamConfig.instance.load();
  runApp(const CamMonitoringApp());
}

class CamMonitoringApp extends StatelessWidget {
  const CamMonitoringApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Cam Monitoring',
      theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
      home: const PhoneHomeScreen(),
    );
  }
}

class PhoneHomeScreen extends StatelessWidget {
  const PhoneHomeScreen({super.key});

  static final List<_PhoneAppShortcut> _apps = [
    _PhoneAppShortcut(
      title: 'Camera',
      icon: Icons.videocam_rounded,
      builder: (_) => const CameraAppScreen(),
    ),
    _PhoneAppShortcut(
      title: 'Settings',
      icon: Icons.settings_rounded,
      builder: (_) => const NgrokSettingsScreen(),
    ),
    _PhoneAppShortcut(
      title: 'Analytics',
      icon: Icons.analytics_rounded,
      builder: (_) => const PlaceholderScreen(title: 'Analytics'),
    ),
    _PhoneAppShortcut(
      title: 'Alerts',
      icon: Icons.notifications_active_rounded,
      builder: (_) => const PlaceholderScreen(title: 'Alerts'),
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('My Phone')),
      body: ValueListenableBuilder<String>(
        valueListenable: StreamConfig.instance.baseUrl,
        builder: (context, baseUrl, _) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: Text(
                  'Connected to: $baseUrl',
                  style: Theme.of(context).textTheme.bodySmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Expanded(
                child: GridView.builder(
                  padding: const EdgeInsets.all(16),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 4,
                    mainAxisSpacing: 18,
                    crossAxisSpacing: 18,
                    childAspectRatio: 0.78,
                  ),
                  itemCount: _apps.length,
                  itemBuilder: (context, index) {
                    final app = _apps[index];
                    return _PhoneAppIcon(app: app);
                  },
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _PhoneAppIcon extends StatelessWidget {
  final _PhoneAppShortcut app;
  const _PhoneAppIcon({required this.app});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () {
        Navigator.of(context).push(
          MaterialPageRoute(builder: app.builder),
        );
      },
      child: Column(
        children: [
          Ink(
            width: 66,
            height: 66,
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.primaryContainer,
              borderRadius: BorderRadius.circular(18),
            ),
            child: Icon(app.icon, size: 30),
          ),
          const SizedBox(height: 8),
          Text(
            app.title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

class _PhoneAppShortcut {
  final String title;
  final IconData icon;
  final WidgetBuilder builder;

  const _PhoneAppShortcut({
    required this.title,
    required this.icon,
    required this.builder,
  });
}

class CameraAppScreen extends StatelessWidget {
  const CameraAppScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Camera')),
      body: const CameraDashboardPage(),
    );
  }
}

class CameraDashboardPage extends StatelessWidget {
  const CameraDashboardPage({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: List.generate(kCameraCount, (i) => CameraViewer(camIndex: i)),
    );
  }
}

class NgrokSettingsScreen extends StatelessWidget {
  const NgrokSettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: const NgrokSettingsPage(),
    );
  }
}

class NgrokSettingsPage extends StatefulWidget {
  const NgrokSettingsPage({super.key});

  @override
  State<NgrokSettingsPage> createState() => _NgrokSettingsPageState();
}

class _NgrokSettingsPageState extends State<NgrokSettingsPage> {
  late final TextEditingController _controller;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: StreamConfig.instance.baseUrl.value);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final value = _controller.text.trim();
    if (value.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter an ngrok URL')),
      );
      return;
    }

    if (!StreamConfig.instance.isValidBaseUrl(value)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Invalid URL. Use http:// or https://')),
      );
      return;
    }

    setState(() {
      _saving = true;
    });

    try {
      await StreamConfig.instance
          .saveBaseUrl(value)
          .timeout(const Duration(seconds: 5));

      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Saved: ${StreamConfig.instance.baseUrl.value}'),
        ),
      );
    } catch (e) {
      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to save URL: $e')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Ngrok / Stream Base URL',
            style: TextStyle(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _controller,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              hintText: 'https://xxxx-xx-xx-xx-xx.ngrok-free.app',
            ),
          ),
          const SizedBox(height: 8),
          ValueListenableBuilder<String>(
            valueListenable: StreamConfig.instance.baseUrl,
            builder: (context, baseUrl, _) {
              return Text(
                'Current: $baseUrl',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              );
            },
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Saving...' : 'Save'),
          ),
        ],
      ),
    );
  }
}

class PlaceholderScreen extends StatelessWidget {
  final String title;
  const PlaceholderScreen({super.key, required this.title});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Center(
        child: Text(
          '$title app is not yet configured.',
          style: Theme.of(context).textTheme.titleMedium,
        ),
      ),
    );
  }
}
