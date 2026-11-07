export function Icon({
  name,
  size = 20,
}: {
  name: 'box' | 'arrow' | 'search' | 'pin' | 'truck' | 'check' | 'refresh' | 'info' | 'leaf';
  size?: number;
}) {
  const paths = {
    box: (
      <>
        <path d="m3 7 9-4 9 4-9 4-9-4Z" />
        <path d="M3 7v10l9 4 9-4V7M12 11v10M7.5 5l9 4" />
      </>
    ),
    arrow: (
      <>
        <path d="M5 12h14m-5-5 5 5-5 5" />
      </>
    ),
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4 4" />
      </>
    ),
    pin: (
      <>
        <path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" />
        <circle cx="12" cy="10" r="2" />
      </>
    ),
    truck: (
      <>
        <path d="M2 5h12v12H2zM14 9h4l4 4v4h-8" />
        <circle cx="6" cy="18" r="2" />
        <circle cx="18" cy="18" r="2" />
      </>
    ),
    check: (
      <>
        <path d="m5 12 4 4L19 6" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 7v5h-5M4 17v-5h5M5.5 7a8 8 0 0 1 13-.5L20 12M4 12l1.5 5.5a8 8 0 0 0 13-.5" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v6m0-11v1" />
      </>
    ),
    leaf: (
      <>
        <path d="M20 3C7 2 2 8 5 15c6 7 16 0 15-12Z" />
        <path d="M4 21 15 9M8 17v-5m0 5h5" />
      </>
    ),
  };
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

export function ProductPlaceholder({ index }: { index: number }) {
  return (
    <div className={`product-image tone-${index % 3}`} role="img" aria-label="商品图片占位图">
      <svg width="33" height="49" viewBox="0 0 40 60" fill="none" aria-hidden="true">
        <rect x="12" y="3" width="16" height="9" rx="2" fill="currentColor" opacity=".65" />
        <rect
          x="8"
          y="13"
          width="24"
          height="42"
          rx="6"
          fill="currentColor"
          opacity=".13"
          stroke="currentColor"
        />
        <rect x="8" y="27" width="24" height="17" fill="#fff" opacity=".9" />
        <path d="M17 35h6m-3-3v6" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    </div>
  );
}
