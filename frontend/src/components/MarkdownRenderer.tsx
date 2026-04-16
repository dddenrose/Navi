import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface MarkdownRendererProps {
  content: string;
}

const components: Components = {
  // Open links in new tab
  a: ({ href, children, ...props }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
      {children}
    </a>
  ),
  // Code blocks & inline code
  code: ({ className, children, ...props }) => {
    const match = /language-(\w+)/.exec(className || "");
    const isBlock = typeof children === "string" && children.includes("\n");
    if (isBlock || match) {
      return (
        <div className="md-code-block">
          {match && <div className="md-code-lang">{match[1]}</div>}
          <pre>
            <code className={className} {...props}>
              {children}
            </code>
          </pre>
        </div>
      );
    }
    return (
      <code className="md-inline-code" {...props}>
        {children}
      </code>
    );
  },
  // Tables
  table: ({ children, ...props }) => (
    <div className="md-table-wrapper">
      <table {...props}>{children}</table>
    </div>
  ),
};

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="md-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
