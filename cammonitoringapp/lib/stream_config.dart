import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

class StreamConfig {
  StreamConfig._();

  static final StreamConfig instance = StreamConfig._();

  static const _keyBaseUrl = 'stream_base_url';

  final ValueNotifier<String> baseUrl =
      ValueNotifier<String>('http://127.0.0.1:5000');

  Future<SharedPreferences?> _prefsOrNull() async {
    try {
      return await SharedPreferences.getInstance();
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }

  Future<void> load() async {
    final prefs = await _prefsOrNull();
    if (prefs == null) {
      return;
    }
    final saved = prefs.getString(_keyBaseUrl);
    if (saved != null && saved.trim().isNotEmpty) {
      baseUrl.value = saved.trim();
    }
  }

  Future<void> saveBaseUrl(String value) async {
    final normalized = _normalizeBaseUrl(value);
    final prefs = await _prefsOrNull();
    if (prefs != null) {
      await prefs.setString(_keyBaseUrl, normalized);
      final stored = prefs.getString(_keyBaseUrl);
      baseUrl.value = stored ?? normalized;
      return;
    }
    baseUrl.value = normalized;
  }

  bool isValidBaseUrl(String value) {
    final normalized = _normalizeBaseUrl(value);
    final uri = Uri.tryParse(normalized);
    return uri != null && (uri.scheme == 'http' || uri.scheme == 'https') && uri.host.isNotEmpty;
  }

  String _normalizeBaseUrl(String value) {
    return value.trim().replaceAll(RegExp(r'/$'), '');
  }
}
