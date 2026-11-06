import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import '../services/api_client.dart';
import '../theme/app_theme.dart';

/// メールアドレスとパスワードだけで完結するログイン画面。
/// 初回は「新規登録」として同じAPIを叩くと、その場でアカウントが作られる。
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _pwCtrl = TextEditingController();
  bool _isNew = false;
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _emailCtrl.dispose();
    _pwCtrl.dispose();
    super.dispose();
  }

  String _toMessage(Object e) {
    final ApiException? ex = e is ApiException ? e : null;
    if (ex == null) {
      return 'ログインできませんでした。時間をおいてもう一度お試しください。';
    }
    switch (ex.code) {
      case 'invalid_credentials':
      case 'invalid_login':
        return 'メールアドレスまたはパスワードが違います。';
      case 'invalid_email':
        return 'メールアドレスの形式が正しくありません。';
      case 'password_too_short':
        return 'パスワードが短すぎます。8文字以上で入力してください。';
      case 'network':
        return '通信できませんでした。電波の良い場所でもう一度お試しください。';
      case 'unauthorized':
        return 'ログインの有効期限が切れました。もう一度お試しください。';
      default:
        return ex.message;
    }
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    FocusScope.of(context).unfocus();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await context.read<AppState>().loginWithPassword(_emailCtrl.text.trim(), _pwCtrl.text);
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = _toMessage(e);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.navyDeep,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        foregroundColor: AppColors.goldLight,
        title: const Text('ログイン', style: TextStyle(fontSize: 16, letterSpacing: 1, fontWeight: FontWeight.w600)),
        centerTitle: true,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(28, 8, 28, 32),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 8),
                Text(
                  _isNew ? 'アカウントを作る' : 'おかえりなさい',
                  style: const TextStyle(color: Colors.white, fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: 1),
                ),
                const SizedBox(height: 10),
                Text(
                  _isNew
                      ? 'メールアドレスとパスワードだけで作れます。命式・会話・人物帳は、このアカウントに保存されます。'
                      : '前回の続きから開きます。命式・会話・人物帳はそのまま残っています。',
                  style: const TextStyle(color: Colors.white70, fontSize: 13, height: 1.7),
                ),
                const SizedBox(height: 26),
                _label('メールアドレス'),
                TextFormField(
                  controller: _emailCtrl,
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                  autofillHints: const [AutofillHints.email],
                  style: const TextStyle(color: AppColors.ink),
                  decoration: _deco('you@example.com'),
                  validator: (v) {
                    final s = (v ?? '').trim();
                    if (s.isEmpty) return 'メールアドレスを入力してください';
                    if (_isNew && (!s.contains('@') || !s.contains('.'))) return 'メールアドレスの形式が正しくありません';
                    return null;
                  },
                ),
                const SizedBox(height: 18),
                _label('パスワード'),
                TextFormField(
                  controller: _pwCtrl,
                  obscureText: _obscure,
                  textInputAction: TextInputAction.done,
                  autofillHints: const [AutofillHints.password],
                  onFieldSubmitted: (_) => _busy ? null : _submit(),
                  style: const TextStyle(color: AppColors.ink),
                  decoration: _deco(_isNew ? '8文字以上' : 'パスワード').copyWith(
                    suffixIcon: IconButton(
                      icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility, color: AppColors.inkSoft, size: 20),
                      onPressed: () => setState(() => _obscure = !_obscure),
                    ),
                  ),
                  validator: (v) {
                    final s = v ?? '';
                    if (s.isEmpty) return 'パスワードを入力してください';
                    if (_isNew && s.length < 8) return '8文字以上で入力してください';
                    return null;
                  },
                ),
                if (_error != null) ...[
                  const SizedBox(height: 16),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: const Color(0xFF7A1F1F).withValues(alpha: 0.35),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: const Color(0xFFE57373).withValues(alpha: 0.5)),
                    ),
                    child: Text(_error!, style: const TextStyle(color: Color(0xFFFFCDD2), fontSize: 13, height: 1.6)),
                  ),
                ],
                const SizedBox(height: 26),
                SizedBox(
                  width: double.infinity,
                  height: 54,
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.gold,
                      foregroundColor: AppColors.navyDeep,
                      disabledBackgroundColor: AppColors.gold.withValues(alpha: 0.4),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    ),
                    onPressed: _busy ? null : _submit,
                    child: _busy
                        ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.navyDeep))
                        : Text(_isNew ? 'この内容で登録する' : 'ログインする', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, letterSpacing: 1)),
                  ),
                ),
                const SizedBox(height: 14),
                Center(
                  child: TextButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() {
                              _isNew = !_isNew;
                              _error = null;
                            }),
                    child: Text(
                      _isNew ? 'すでにアカウントをお持ちの方' : 'はじめての方（アカウントを作る）',
                      style: const TextStyle(color: AppColors.goldLight, fontSize: 13.5, decoration: TextDecoration.underline, decorationColor: Colors.white38),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'パスワードは再設定できません。忘れないよう、端末のパスワード管理に保存してください。',
                  style: TextStyle(color: Colors.white38, fontSize: 11.5, height: 1.6),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _label(String t) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(t, style: const TextStyle(color: Colors.white70, fontSize: 12, letterSpacing: 0.5)),
      );

  InputDecoration _deco(String hint) => InputDecoration(
        hintText: hint,
        hintStyle: const TextStyle(color: AppColors.inkSoft, fontSize: 15),
        filled: true,
        fillColor: Colors.white,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: AppColors.gold, width: 1.5)),
        errorStyle: const TextStyle(color: Color(0xFFFFCDD2), fontSize: 12),
      );
}
