import { cloneElement, isValidElement, type ReactElement } from "react";

interface FieldControlProps {
  "aria-describedby"?: string;
  "aria-errormessage"?: string;
  "aria-invalid"?: boolean;
}

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
  const field = children as ReactElement<FieldControlProps>;
  const describedBy = [field.props["aria-describedby"], error || hint ? descriptionId : undefined]
    .filter(Boolean)
    .join(" ") || undefined;
  const control = isValidElement(children)
    ? cloneElement(field, {
        "aria-describedby": describedBy,
        "aria-errormessage": error ? descriptionId : undefined,
        "aria-invalid": error ? true : undefined,
      })
    : children;
  return (
    <div className={`form-field ${error ? "has-error" : ""}`}>
      <label htmlFor={htmlFor}>{label}</label>
      {control}
      {(error || hint) && (
        <span id={descriptionId} className="form-field__message" role={error ? "alert" : undefined}>
          {error ?? hint}
        </span>
      )}
    </div>
  );
}
