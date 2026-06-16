// Legitimate framework syntax below — a smart scanner must NOT flag any of it.
import { useState } from "react";

export function UserCard({ user }) {
  const [open, setOpen] = useState(false);      // destructuring: not a placeholder
  const cols = user.roles[0];                     // index access: not a placeholder
  const slugPattern = /[a-z0-9-]+/;               // regex char-class: not a placeholder
  const route = `/users/[id]/posts/[tag]`;        // Next.js route params: not slop

  return (
    <article className="user-card">
      <a href={`/city/[city]/[username]`}>View profile</a>
      <input type="checkbox" [checked]="open" />  {/* Angular binding: not slop */}
      <h2>{user.name}</h2>

      {/* This one IS real AI slop and SHOULD be flagged: */}
      <p>Welcome to [Your Company Name] — edit this before launch.</p>
    </article>
  );
}
