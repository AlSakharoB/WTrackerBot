import { cloneElement, isValidElement, type ReactElement } from "react";

interface FormFieldProps {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  children: ReactElement;
}

export function FormField({
  label,
  htmlFor,
  hint,
  error,
  children,
}: FormFieldProps) {
  const descriptionId = `${htmlFor}-description`;
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<{
        "aria-describedby"?: string;
        "aria-invalid"?: boolean;
      }>, {
        "aria-describedby": error || hint ? descriptionId : undefined,
        "aria-invalid": error ? true : undefined,
      })
    : children;
  return (
    <div className={`form-field ${error ? "has-error" : ""}`}>
      <label htmlFor={htmlFor}>{label}</label>
      {control}
      {(error || hint) && (
        <span id={descriptionId} className="form-field__message">
          {error ?? hint}
        </span>
      )}
    </div>
  );
}
