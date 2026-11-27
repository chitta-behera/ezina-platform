import { ButtonLink } from "@ezina/ui";

export default function NotFound() {
  return (
    <section className="container-page py-24 text-center">
      <h1 className="font-display text-4xl font-bold text-navy-deep">Page not found</h1>
      <p className="mt-3 text-muted">The page you were looking for doesn&apos;t exist.</p>
      <div className="mt-8">
        <ButtonLink href="/">Back to the home page</ButtonLink>
      </div>
    </section>
  );
}
