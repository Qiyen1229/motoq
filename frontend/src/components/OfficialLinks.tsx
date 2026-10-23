import { useState } from "react";

interface L { title: string; note: string; url: string }

const TOPICS: Record<string, { heading: string; why: string; links: L[] }> = {
  fines: {
    heading: "怎麼查違規罰單",
    why: "違規罰單屬於個資，官方只開放用「身分證字號＋生日／統編＋驗證碼」查詢，沒有只憑車牌的公開 API，所以無法在這裡自動查詢。",
    links: [
      { title: "交通違規（含強制險）查詢及繳納", note: "監理服務網", url: "https://www.mvdis.gov.tw/m3-emv-vil/vil/penaltyQueryPay" },
      { title: "汽機車違規記次查詢", note: "監理服務網", url: "https://www.mvdis.gov.tw/m3-emv-vil/vil/carPenalty" },
    ],
  },
  etag: {
    heading: "查 etag 官方餘額與欠費",
    why: "遠通電收的餘額、通行紀錄與欠費需以車號＋車主證號登入查詢，沒有開放 API。這裡的餘額由你記錄的儲值與通行費推算，可用「校正」與官方對齊。",
    links: [
      { title: "遠通電收（官網／ETC App）", note: "儲值、查餘額、查欠費", url: "https://www.fetc.net.tw/" },
      { title: "如何查詢 eTag 預儲帳戶餘額", note: "交通部高速公路局", url: "https://www.freeway.gov.tw/etc/QADetail.aspx?QID=155" },
      { title: "欠費查詢及催繳通知", note: "交通部高速公路局", url: "https://www.freeway.gov.tw/etc/publish.aspx?NID=1941&P=9101" },
    ],
  },
  tax: {
    heading: "稅費繳納與查詢",
    why: "牌照稅每年 4 月繳納；燃料費（公路養管費）與欠稅查詢需登入或輸入證號，請至官方管道辦理。",
    links: [
      { title: "使用牌照稅稅額表", note: "臺北市稅捐稽徵處", url: "https://tpctax.gov.taipei/News_Content.aspx?n=87EECD3D91B2159E&sms=36C4085CDE198F4C&s=5D2ED0F9A79080F8" },
      { title: "監理服務網", note: "燃料費／養管費、驗車、車籍", url: "https://www.mvdis.gov.tw/" },
    ],
  },
};

export default function OfficialLinks({ topic }: { topic: keyof typeof TOPICS }) {
  const t = TOPICS[topic];
  const [open, setOpen] = useState(false);
  return (
    <section className="card space-y-2">
      <button type="button" className="flex w-full items-center justify-between text-left" onClick={() => setOpen(!open)}>
        <span className="text-sm font-semibold">{t.heading}</span>
        <span className="text-xs gold-text">{open ? "收合" : "展開"}</span>
      </button>
      {open && (
        <div className="space-y-3">
          <p className="text-xs leading-relaxed text-slate-500">{t.why}</p>
          <ul className="space-y-2">
            {t.links.map((l) => (
              <li key={l.url}>
                <a href={l.url} target="_blank" rel="noreferrer noopener"
                  className="flex items-center justify-between rounded-xl bg-slate-100 px-3 py-2.5 text-sm dark:bg-slate-800">
                  <span>
                    <span className="block font-medium">{l.title}</span>
                    <span className="block text-xs text-slate-500">{l.note}</span>
                  </span>
                  <span className="gold-text">↗</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
