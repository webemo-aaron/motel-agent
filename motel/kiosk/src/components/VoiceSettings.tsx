import { useState, useEffect } from 'react';

interface VoiceSettings {
  'voice.public_host'?: string;
  'voice.hermes_url'?: string;
  'voice.hermes_api_key'?: string;
  'voice.twilio_account_sid'?: string;
  'voice.twilio_auth_token'?: string;
  'voice.twilio_phone_number'?: string;
  'voice.ifttt_webhook_key'?: string;
  'voice.ifttt_event_name'?: string;
}

interface VoiceStatus {
  voice_bridge_healthy: boolean;
  public_host: string;
  twilio_configured: boolean;
}

export function VoiceSettings() {
  const [settings, setSettings] = useState<VoiceSettings>({});
  const [status, setStatus] = useState<VoiceStatus>({
    voice_bridge_healthy: false,
    public_host: '',
    twilio_configured: false,
  });
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  // Fetch settings on mount and refresh status
  useEffect(() => {
    fetchSettings();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchSettings = async () => {
    try {
      const resp = await fetch('/api/motel/settings/voice');
      if (resp.ok) {
        setSettings(await resp.json());
      }
    } catch (err) {
      console.error('Failed to fetch settings:', err);
    }
  };

  const fetchStatus = async () => {
    try {
      const resp = await fetch('/api/voice/status');
      if (resp.ok) {
        setStatus(await resp.json());
      }
    } catch (err) {
      console.error('Failed to fetch voice status:', err);
    }
  };

  const handleInputChange = (key: string, value: string) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage('');

    const body: Record<string, string | null> = {};
    const keyMap: Record<string, string> = {
      'voice.public_host': 'public_host',
      'voice.hermes_url': 'hermes_url',
      'voice.hermes_api_key': 'hermes_api_key',
      'voice.twilio_account_sid': 'twilio_account_sid',
      'voice.twilio_auth_token': 'twilio_auth_token',
      'voice.twilio_phone_number': 'twilio_phone_number',
      'voice.ifttt_webhook_key': 'ifttt_webhook_key',
      'voice.ifttt_event_name': 'ifttt_event_name',
    };

    for (const [key, field] of Object.entries(keyMap)) {
      const val = settings[key as keyof VoiceSettings] || '';
      // Skip masked fields (still have ●●●● pattern)
      if (val && !val.startsWith('●●●●')) {
        body[field] = val;
      }
    }

    try {
      const resp = await fetch('/api/motel/settings/voice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (resp.ok) {
        setMessage('✓ Configuration saved');
        await new Promise(r => setTimeout(r, 500));
        fetchSettings();
        fetchStatus();
      } else {
        setMessage('✗ Failed to save');
      }
    } catch (err) {
      console.error('Save error:', err);
      setMessage('✗ Error saving configuration');
    }

    setSaving(false);
  };

  const togglePassword = (key: string) => {
    setShowPasswords(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const getFieldLabel = (key: string): string => {
    const labels: Record<string, string> = {
      'voice.public_host': 'Tunnel URL (PUBLIC_HOST)',
      'voice.hermes_url': 'Hermes Gateway URL',
      'voice.hermes_api_key': 'Hermes API Key',
      'voice.twilio_account_sid': 'Twilio Account SID',
      'voice.twilio_auth_token': 'Twilio Auth Token',
      'voice.twilio_phone_number': 'Twilio Phone Number',
      'voice.ifttt_webhook_key': 'IFTTT Webhook Key',
      'voice.ifttt_event_name': 'IFTTT Event Name',
    };
    return labels[key] || key;
  };

  const isMasked = (val: string | undefined): boolean => val?.startsWith('●●●●') ?? false;
  const secretKeys = new Set([
    'voice.hermes_api_key',
    'voice.twilio_auth_token',
    'voice.ifttt_webhook_key',
  ]);

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-8">
      <h1 className="text-3xl font-bold text-white">🔊 Voice Configuration</h1>

      {/* Status Panel */}
      <div className="bg-slate-800 rounded-lg p-6 space-y-4 border border-slate-700">
        <h2 className="text-xl font-semibold text-white">Status</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center space-x-2">
            <span className={`inline-block w-3 h-3 rounded-full ${status.voice_bridge_healthy ? 'bg-green-500' : 'bg-red-500'}`}></span>
            <span className="text-slate-300">Voice Bridge</span>
            <span className="text-white font-semibold ml-auto">{status.voice_bridge_healthy ? '✓ Running' : '✗ Offline'}</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className={`inline-block w-3 h-3 rounded-full ${status.public_host ? 'bg-green-500' : 'bg-gray-500'}`}></span>
            <span className="text-slate-300">Tunnel</span>
            <span className="text-white font-semibold ml-auto">{status.public_host || '— Not set'}</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className={`inline-block w-3 h-3 rounded-full ${status.twilio_configured ? 'bg-green-500' : 'bg-yellow-500'}`}></span>
            <span className="text-slate-300">Twilio</span>
            <span className="text-white font-semibold ml-auto">{status.twilio_configured ? '✓ Configured' : '⚠ Not set'}</span>
          </div>
        </div>
      </div>

      {/* Settings Form */}
      <div className="space-y-6">
        {/* Phone Configuration */}
        <div className="bg-slate-800 rounded-lg p-6 space-y-4 border border-slate-700">
          <h3 className="text-lg font-semibold text-white">Phone (Twilio)</h3>
          {['voice.public_host', 'voice.twilio_account_sid', 'voice.twilio_auth_token', 'voice.twilio_phone_number'].map(key => (
            <div key={key} className="space-y-1">
              <label className="block text-sm font-medium text-slate-300">{getFieldLabel(key)}</label>
              <div className="flex gap-2">
                <input
                  type={secretKeys.has(key) && !showPasswords[key] ? 'password' : 'text'}
                  value={settings[key as keyof VoiceSettings] || ''}
                  onChange={e => handleInputChange(key, e.target.value)}
                  disabled={isMasked(settings[key as keyof VoiceSettings])}
                  className="flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 disabled:opacity-50"
                  placeholder={`Enter ${getFieldLabel(key).toLowerCase()}`}
                />
                {secretKeys.has(key) && isMasked(settings[key as keyof VoiceSettings]) && (
                  <button
                    onClick={() => togglePassword(key)}
                    className="px-3 py-2 bg-slate-600 hover:bg-slate-500 rounded text-sm text-white font-medium"
                  >
                    {showPasswords[key] ? 'hide' : 'show'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Agent Gateway */}
        <div className="bg-slate-800 rounded-lg p-6 space-y-4 border border-slate-700">
          <h3 className="text-lg font-semibold text-white">Agent Gateway</h3>
          {['voice.hermes_url', 'voice.hermes_api_key'].map(key => (
            <div key={key} className="space-y-1">
              <label className="block text-sm font-medium text-slate-300">{getFieldLabel(key)}</label>
              <div className="flex gap-2">
                <input
                  type={secretKeys.has(key) && !showPasswords[key] ? 'password' : 'text'}
                  value={settings[key as keyof VoiceSettings] || ''}
                  onChange={e => handleInputChange(key, e.target.value)}
                  disabled={isMasked(settings[key as keyof VoiceSettings])}
                  className="flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 disabled:opacity-50"
                  placeholder={`Enter ${getFieldLabel(key).toLowerCase()}`}
                />
                {secretKeys.has(key) && isMasked(settings[key as keyof VoiceSettings]) && (
                  <button
                    onClick={() => togglePassword(key)}
                    className="px-3 py-2 bg-slate-600 hover:bg-slate-500 rounded text-sm text-white font-medium"
                  >
                    {showPasswords[key] ? 'hide' : 'show'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* IFTTT Configuration */}
        <div className="bg-slate-800 rounded-lg p-6 space-y-4 border border-slate-700">
          <h3 className="text-lg font-semibold text-white">IFTTT Camera Wake</h3>
          {['voice.ifttt_webhook_key', 'voice.ifttt_event_name'].map(key => (
            <div key={key} className="space-y-1">
              <label className="block text-sm font-medium text-slate-300">{getFieldLabel(key)}</label>
              <div className="flex gap-2">
                <input
                  type={secretKeys.has(key) && !showPasswords[key] ? 'password' : 'text'}
                  value={settings[key as keyof VoiceSettings] || ''}
                  onChange={e => handleInputChange(key, e.target.value)}
                  disabled={isMasked(settings[key as keyof VoiceSettings])}
                  className="flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 disabled:opacity-50"
                  placeholder={`Enter ${getFieldLabel(key).toLowerCase()}`}
                />
                {secretKeys.has(key) && isMasked(settings[key as keyof VoiceSettings]) && (
                  <button
                    onClick={() => togglePassword(key)}
                    className="px-3 py-2 bg-slate-600 hover:bg-slate-500 rounded text-sm text-white font-medium"
                  >
                    {showPasswords[key] ? 'hide' : 'show'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Save Button & Message */}
      <div className="flex gap-4 items-center">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-6 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 rounded font-semibold text-white"
        >
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>
        {message && (
          <span className={`text-sm font-medium ${message.startsWith('✓') ? 'text-green-400' : 'text-red-400'}`}>
            {message}
          </span>
        )}
      </div>
    </div>
  );
}
