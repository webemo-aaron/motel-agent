import React, { useEffect, useRef, useState } from 'react';

// Web Speech API type definitions (avoiding interface/class confusion)
interface SpeechRecognitionResult {
  isFinal: boolean;
  [index: number]: SpeechRecognitionAlternative;
  length: number;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionResultList {
  [index: number]: SpeechRecognitionResult;
  length: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
}

interface ISpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  language: string;
  onstart: ((event: Event) => void) | null;
  onend: ((event: Event) => void) | null;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

declare global {
  interface Window {
    SpeechRecognition?: any;
    webkitSpeechRecognition?: any;
  }
}

interface VoiceChatProps {
  onMessage: (text: string) => void;
  onSpeechStart?: () => void;
  onSpeechEnd?: () => void;
}

export function VoiceChat({ onMessage, onSpeechStart, onSpeechEnd }: VoiceChatProps) {
  const [isListening, setIsListening] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const recognitionRef = useRef<ISpeechRecognition | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Initialize speech recognition
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('SpeechRecognition not supported in this browser');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.language = 'en-US';

    recognition.onstart = () => {
      setIsListening(true);
      onSpeechStart?.();
    };

    recognition.onend = () => {
      setIsListening(false);
      onSpeechEnd?.();
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0].transcript)
        .join('');

      if (transcript.trim()) {
        onMessage(transcript);
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
    };

    recognitionRef.current = recognition;

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }
    };
  }, [onMessage, onSpeechStart, onSpeechEnd]);

  // Listen for camera wake triggers via SSE
  useEffect(() => {
    const eventSource = new EventSource('/api/voice/wake');

    eventSource.onmessage = (event) => {
      if (event.data === 'start') {
        startListening();
      }
    };

    eventSource.onerror = (error) => {
      console.error('Voice wake connection error:', error);
      eventSource.close();
    };

    eventSourceRef.current = eventSource;

    return () => {
      eventSource.close();
    };
  }, []);

  const startListening = () => {
    if (!recognitionRef.current || isListening) return;
    recognitionRef.current.start();
  };

  const stopListening = () => {
    if (!recognitionRef.current) return;
    recognitionRef.current.stop();
  };

  return (
    <div className="voice-chat-controls flex gap-2 items-center">
      <button
        onMouseDown={startListening}
        onMouseUp={stopListening}
        onTouchStart={startListening}
        onTouchEnd={stopListening}
        className={`px-4 py-2 rounded-lg font-semibold transition-all ${
          isListening
            ? 'bg-red-500 text-white shadow-lg animate-pulse'
            : 'bg-blue-500 text-white hover:bg-blue-600'
        }`}
        title="Press and hold to record your voice"
      >
        {isListening ? '🔴 Listening...' : '🎤 Press & Hold'}
      </button>

      <button
        onClick={() => setIsMuted(!isMuted)}
        className={`px-3 py-2 rounded-lg transition-all ${
          isMuted
            ? 'bg-gray-400 text-white'
            : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
        }`}
        title={isMuted ? 'Unmute responses' : 'Mute voice responses'}
      >
        {isMuted ? '🔇' : '🔊'}
      </button>
    </div>
  );
}

export function speakText(text: string, rate: number = 0.95): void {
  if (!('speechSynthesis' in window)) {
    console.warn('SpeechSynthesis not supported');
    return;
  }

  // Cancel any ongoing speech
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = rate;
  utterance.pitch = 0.9;
  utterance.volume = 1;

  window.speechSynthesis.speak(utterance);
}
