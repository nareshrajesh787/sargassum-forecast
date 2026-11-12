import type { HeadlineRow } from "@/lib/types";
import { num } from "@/lib/colors";

export default function HeadlineTable({ rows, season }: { rows: HeadlineRow[]; season: string }) {
  const r = rows.filter((x) => x.season === season);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>Model</th><th>Inputs</th><th className="num">Brier skill vs climatology</th><th className="num">95% CI</th><th className="num">ROC-AUC</th></tr>
        </thead>
        <tbody>
          {r.map((x) => (
            <tr key={x.model}>
              <td><strong>{x.model}</strong><div className="muted" style={{ fontSize: 12 }}>{x.description}</div></td>
              <td><span className="tag">{x.upper_bound ? "target-day weather (upper bound)" : "issue-time only"}</span></td>
              <td className="num">{num(x.bss_vs_climatology)}</td>
              <td className="num">[{num(x.bss_ci[0])}, {num(x.bss_ci[1])}]</td>
              <td className="num">{num(x.auc)} [{num(x.auc_ci[0])}, {num(x.auc_ci[1])}]</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
