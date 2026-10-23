import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "../api";
import Icon from "./Icon";
import { ConfirmButton, ErrorText } from "./ui";

/** 單據照片：上傳後由伺服器壓縮並移除 EXIF（含 GPS），不經任何第三方。 */
export default function Attachments({ ownerType, ownerId, title = "單據照片" }: {
  ownerType: string; ownerId: number; title?: string;
}) {
  const qc = useQueryClient();
  const key = ["attachments", ownerType, ownerId];
  const list = useQuery({ queryKey: key, queryFn: () => api.attachments(ownerType, ownerId) });
  const input = useRef<HTMLInputElement>(null);
  const [viewing, setViewing] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      for (const f of Array.from(files)) await api.uploadAttachment(ownerType, ownerId, f);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ["visits"] }); },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteAttachment(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });

  return (
    <section className="card space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">{title}</h2>
        <button type="button" className="btn-ghost btn-sm" onClick={() => input.current?.click()} disabled={upload.isPending}>
          <Icon name="camera" className="h-4 w-4" />
          {upload.isPending ? "上傳中…" : "新增照片"}
        </button>
        <input ref={input} type="file" accept="image/*" multiple capture={undefined} className="hidden"
          onChange={(e) => { if (e.target.files?.length) upload.mutate(e.target.files); e.target.value = ""; }} />
      </div>
      <ErrorText error={upload.error ?? remove.error} />
      {list.data?.length ? (
        <ul className="grid grid-cols-3 gap-2">
          {list.data.map((a) => (
            <li key={a.id} className="space-y-1">
              <button type="button" onClick={() => setViewing(a.url)} className="block aspect-square w-full overflow-hidden rounded-lg ring-1 ring-slate-300 dark:ring-slate-700">
                <img src={a.thumb_url} alt={a.original_name || "單據"} className="h-full w-full object-cover" loading="lazy" />
              </button>
              <ConfirmButton onConfirm={() => remove.mutate(a.id)} className="btn-danger btn-sm w-full !min-h-[32px] text-xs">刪除</ConfirmButton>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">尚未附上照片。圖片會在伺服器端壓縮並移除位置資訊。</p>
      )}
      {viewing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-3" onClick={() => setViewing(null)} role="dialog">
          <img src={viewing} alt="單據大圖" className="max-h-full max-w-full rounded-lg" />
        </div>
      )}
    </section>
  );
}
