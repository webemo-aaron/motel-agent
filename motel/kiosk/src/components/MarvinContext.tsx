import { useEffect, useState } from "react";

interface MarvinDecision {
  type: "priority" | "recommendation" | "alert" | "guest_context";
  priority: "critical" | "high" | "medium" | "low";
  message: string;
  context?: Record<string, unknown>;
  timestamp: string;
}

interface MarvinContextProps {
  occupancyPct: number;
  dirtyRooms: number;
  arrivals: number;
  unresolvedAlerts: number;
}

export default function MarvinContext({
  occupancyPct,
  dirtyRooms,
  arrivals,
  unresolvedAlerts,
}: MarvinContextProps) {
  const [decisions, setDecisions] = useState<MarvinDecision[]>([]);

  useEffect(() => {
    const newDecisions: MarvinDecision[] = [];

    // Critical: Unresolved alerts
    if (unresolvedAlerts > 0) {
      newDecisions.push({
        type: "alert",
        priority: "critical",
        message: `${unresolvedAlerts} unresolved alert${unresolvedAlerts !== 1 ? "s" : ""}. Check Telegram immediately.`,
        timestamp: new Date().toISOString(),
      });
    }

    // High priority: Occupancy strategy
    if (occupancyPct > 80) {
      newDecisions.push({
        type: "recommendation",
        priority: "high",
        message: "High occupancy (>80%). Prioritize same-day arrivals for turnover.",
        context: { occupancyPct },
        timestamp: new Date().toISOString(),
      });
    }

    // High priority: Dirty rooms with arrivals
    if (dirtyRooms > 0 && arrivals > 0) {
      newDecisions.push({
        type: "priority",
        priority: "high",
        message: `${dirtyRooms} dirty room${dirtyRooms !== 1 ? "s" : ""} with ${arrivals} arrival${arrivals !== 1 ? "s" : ""} today. Coordinate with housekeeping on turnover priority.`,
        context: { dirtyRooms, arrivals },
        timestamp: new Date().toISOString(),
      });
    }

    // Medium: Low occupancy
    if (occupancyPct < 35) {
      newDecisions.push({
        type: "recommendation",
        priority: "medium",
        message: "Low occupancy (<35%). Consider offering early check-in or upgrades to arriving guests.",
        context: { occupancyPct },
        timestamp: new Date().toISOString(),
      });
    }

    // Medium: Many dirty rooms
    if (dirtyRooms > 5) {
      newDecisions.push({
        type: "recommendation",
        priority: "medium",
        message: "Multiple rooms need cleaning. Confirm housekeeping staffing and turnaround estimates.",
        context: { dirtyRooms },
        timestamp: new Date().toISOString(),
      });
    }

    setDecisions(newDecisions);
  }, [occupancyPct, dirtyRooms, arrivals, unresolvedAlerts]);

  if (decisions.length === 0) {
    return null;
  }

  const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
  const sortedDecisions = [...decisions].sort(
    (a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]
  );

  const priorityColors: Record<string, string> = {
    critical: "bg-red-900 border-red-700",
    high: "bg-orange-900 border-orange-700",
    medium: "bg-yellow-900 border-yellow-700",
    low: "bg-blue-900 border-blue-700",
  };

  const priorityIcons: Record<string, string> = {
    critical: "🚨",
    high: "⚠️",
    medium: "ℹ️",
    low: "💡",
  };

  return (
    <div className="space-y-2">
      <div className="text-slate-300 text-sm font-semibold tracking-wide">
        Marvin's Operational Insights
      </div>
      {sortedDecisions.slice(0, 3).map((decision, idx) => (
        <div
          key={idx}
          className={`border-l-4 p-3 rounded text-sm ${priorityColors[decision.priority]} text-white`}
        >
          <div className="flex items-start gap-2">
            <span className="text-lg">{priorityIcons[decision.priority]}</span>
            <div className="flex-1">
              <div className="font-semibold capitalize">{decision.priority}</div>
              <div className="text-slate-100">{decision.message}</div>
            </div>
          </div>
        </div>
      ))}
      {decisions.length > 3 && (
        <div className="text-slate-400 text-xs">
          +{decisions.length - 3} more insight{decisions.length - 3 !== 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}
