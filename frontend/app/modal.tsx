"use client";
import { useEffect, useRef, type ReactNode } from "react";

export function Modal({
  label,
  onClose,
  children,
}: {
  label: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    element?.querySelector<HTMLInputElement>("input")?.focus();
    return () => element?.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="modal-dialog"
      aria-labelledby={label}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      {children}
    </dialog>
  );
}
