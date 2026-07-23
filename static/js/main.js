/* Shared client-side behaviour. Loaded with `defer` on every page;
   each feature no-ops when its markup is absent. */

/* ----- Live preview for file inputs -----
   Usage: <input type="file" data-preview="<img id>"> */
document.addEventListener("change", (event) => {
  const input = event.target;
  if (
    input.matches('input[type="file"][data-preview]') &&
    input.files &&
    input.files[0]
  ) {
    const img = document.getElementById(input.dataset.preview);
    if (img) img.src = URL.createObjectURL(input.files[0]);
  }
});

/* ----- Infinite scroll for the pin feed -----
   home.html renders page 1 plus a sentinel carrying the feed state;
   nearing the sentinel fetches the next page from /api/pins. */
(function () {
  const sentinel = document.getElementById("feed-sentinel");
  const grid = document.getElementById("pin-grid");
  if (!sentinel || !grid) return;

  const spinner = document.getElementById("feed-spinner");
  let page = 1;
  let loading = false;
  let hasMore = sentinel.dataset.hasMore === "1";

  async function loadNextPage() {
    if (loading || !hasMore) return;
    loading = true;
    spinner.hidden = false;
    try {
      const params = new URLSearchParams({
        page: page + 1,
        seed: sentinel.dataset.seed,
        category: sentinel.dataset.category,
        q: sentinel.dataset.q,
      });
      const resp = await fetch("/api/pins?" + params);
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      const data = await resp.json();
      grid.insertAdjacentHTML("beforeend", data.html);
      page += 1;
      hasMore = data.has_more;
    } catch (err) {
      console.error("Failed to load more pins:", err);
      hasMore = false; // stop retry-looping on a broken endpoint
    } finally {
      spinner.hidden = true;
      loading = false;
      if (!hasMore) observer.disconnect();
    }
  }

  // Start fetching one viewport-height before the sentinel scrolls in
  const observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting) loadNextPage();
    },
    { rootMargin: "100% 0px" }
  );

  if (hasMore) observer.observe(sentinel);
})();
