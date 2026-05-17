import { useState, useRef, useEffect } from "react";
import { VoiceChat, speakText } from "./VoiceChat";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function AgentChat({ onClose }: { onClose: () => void }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage(textOverride?: string) {
    const text = (textOverride ?? input).trim();
    if (!text || loading) return;

    if (!textOverride) {
      setInput("");
    }

    const newMessages: Message[] = [...messages, { role: "user", content: text }];
    setMessages(newMessages);
    setLoading(true);

    try {
      const resp = await fetch("/api/hermes/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer test-key-for-local-development"
        },
        body: JSON.stringify({
          model: "hermes",
          messages: newMessages.map((m) => ({ role: m.role, content: m.content })),
          stream: false,
        }),
      });
      const data = await resp.json() as { choices?: Array<{ message?: { content?: string } }> };
      const reply = data?.choices?.[0]?.message?.content ?? "(no response)";
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);

      // Speak the reply if voice mode is enabled
      if (voiceEnabled && !isSpeaking) {
        setIsSpeaking(true);
        speakText(reply);
        // Assume ~1.5 seconds per 10 words of speech
        const duration = Math.max(2000, (reply.split(" ").length / 10) * 1500);
        setTimeout(() => setIsSpeaking(false), duration);
      }
    } catch {
      const errorMsg = "Could not reach the local agent. Check that the West Bethel stack is running.";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: errorMsg },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 h-96 bg-slate-900 border-t border-slate-700 flex flex-col shadow-2xl">
      <div className="flex items-center px-4 py-2 border-b border-slate-700 gap-3">
        <span className="font-semibold text-slate-200">Agent Chat</span>
        <button
          onClick={() => setVoiceEnabled(!voiceEnabled)}
          className={`text-sm px-2 py-1 rounded transition-all ${
            voiceEnabled ? "bg-green-600 text-white" : "bg-gray-600 text-gray-300 hover:bg-gray-500"
          }`}
          title="Toggle voice mode (auto-read responses)"
        >
          {voiceEnabled ? "🎙️ Voice On" : "🎙️ Voice Off"}
        </button>
        <span className="flex-1" />
        <button onClick={onClose} className="text-slate-400 hover:text-white text-xl px-2">×</button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-3">
        {messages.length === 0 && (
          <p className="text-slate-500 text-sm">
            Ask the agent: "What rooms are available Friday?", "Move Jane Smith to room 104", "Send a test alert"
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-xl px-4 py-2 rounded-lg text-sm whitespace-pre-wrap ${
                m.role === "user" ? "bg-blue-700" : "bg-slate-700"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-slate-700 px-4 py-2 rounded-lg text-sm text-slate-400 animate-pulse">
              Thinking...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="px-4 py-3 border-t border-slate-700 space-y-2">
        {voiceEnabled && (
          <VoiceChat
            onMessage={(transcript) => void sendMessage(transcript)}
            onSpeechStart={() => setInput("")}
            onSpeechEnd={() => {}}
          />
        )}
        <div className="flex gap-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) void sendMessage(); }}
            placeholder="Ask the agent..."
            className="flex-1 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500"
          />
          <button
            onClick={() => void sendMessage()}
            disabled={loading || !input.trim()}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 px-4 py-2 rounded text-sm font-semibold"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
