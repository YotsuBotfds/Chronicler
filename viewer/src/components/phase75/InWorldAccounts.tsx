import type { EventAccounts } from "../../lib/historiography";
import { capitalized, lossPhrase } from "../../lib/historiography";

/**
 * Event inspector section: how the world's own chroniclers told the selected
 * event. Each account is a recorded, biased telling of the real event above
 * (its transforms name the biases); lost accounts are shown as lost.
 */
export function InWorldAccounts({ accounts }: { accounts: EventAccounts | null }) {
  if (!accounts || accounts.accounts.length === 0) {
    return null;
  }
  const { divergence } = accounts;
  return (
    <div className="phase75-accounts" aria-label="In-world accounts">
      <div className="phase75-stat-row">
        <span>In-world accounts</span>
        <strong>
          {accounts.accounts.length} chronicler{accounts.accounts.length !== 1 ? "s" : ""}
          {divergence.length > 0 && ` · contested (${divergence.join(", ")})`}
        </strong>
      </div>
      <ul className="phase75-account-list">
        {accounts.accounts.map((account) => {
          const kinds = [...new Set(account.transforms.map((t) => t.kind))].sort();
          return (
            <li key={account.id} className={`phase75-account phase75-account-${account.status}`}>
              <span className="phase75-account-source">{capitalized(account.chroniclerName)}</span>
              {kinds.length > 0 && account.status !== "silent" && (
                <span className="phase75-account-tags"> ({kinds.join(", ")})</span>
              )}
              {account.status === "told" && <q className="phase75-account-text">{account.text}</q>}
              {account.status === "plain" && <em> tell it as it happened.</em>}
              {account.status === "silent" && <em> pass over it in silence.</em>}
              {account.status === "lost" && (
                <>
                  <em>
                    {" "}lost: their archive was {lossPhrase(account.lostCause)} (turn {account.lostTurn}).
                  </em>
                  {account.text && <q className="phase75-account-text phase75-account-lost-text">{account.text}</q>}
                </>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
