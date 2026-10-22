import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
export const PALETTE = ["#2E9E5B", "#B8802F", "#7A5CC9", "#C43D3D", "#14171C", "#2B7A9E", "#8FA33A", "#D0679A", "#565C66"];

export function variantsOf(rows) {
  return [...new Set(rows.map((r) => r.variant))].sort();
}

export function MetricChart({ rows, metric, title, yLabel, percent = true }) {
  const variants = variantsOf(rows);
  const rates = [...new Set(rows.map((r) => r.error_rate))].sort((a, b) => a - b);
  const data = rates.map((rate) => {
    const o = { rate: +(rate * 100).toFixed(2) };
    variants.forEach((v) => {
      const r = rows.find((x) => x.variant === v && x.error_rate === rate);
      const val = r ? r[metric] : null;
      o[v] = val == null ? null : percent ? +(val * 100).toFixed(2) : +val.toFixed(2);
    });
    return o;
  });
  return (
    <div className="panel">
      <h3 className="text-base">{title}</h3>
      <div className="mt-3 h-80">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ left: 0, right: 12, top: 8, bottom: 8 }}>
            <CartesianGrid stroke="#DEDBD2" />
            <XAxis
              dataKey="rate"
              tick={{ fontSize: 11 }}
              label={{ value: "channel error rate (%)", position: "insideBottom", offset: -4, fontSize: 11 }}
              height={36}
            />
            <YAxis
              tick={{ fontSize: 11 }}
              width={44}
              label={{ value: yLabel, angle: -90, position: "insideLeft", fontSize: 11 }}
            />
            <Tooltip formatter={(v) => (percent ? `${v}%` : v)} labelFormatter={(l) => `${l}% error`} />
            <Legend verticalAlign="top" height={40} wrapperStyle={{ fontSize: 12 }} />
            {variants.map((v, i) => (
              <Line key={v} dataKey={v} stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} dot={{ r: 3 }} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
