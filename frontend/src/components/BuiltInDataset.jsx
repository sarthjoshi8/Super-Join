import React from "react";

const builtInPDFs = [
    {
        name: "Delhivery Prospectus 2022",
        file: "01-delhivery-prospectus-2022-excerpt.pdf",
    },
    {
        name: "India Economic Survey 2024-25",
        file: "01-india-economic-survey-2024-25-excerpt.pdf",
    },
    {
        name: "Delhivery Annual Report FY24",
        file: "02-delhivery-annual-report-fy24-excerpt.pdf",
    },
    {
        name: "RBI Annual Report 2024-25",
        file: "02-rbi-annual-report-2024-25-excerpt.pdf",
    },
    {
        name: "Delhivery Q4 FY24 Earnings Presentation",
        file: "03-delhivery-q4-fy24-earnings-presentation.pdf",
    },
    {
        name: "IMF India 2025 Article IV",
        file: "03-imf-india-2025-article-iv-excerpt.pdf",
    },
];

export default function BuiltInDataset() {
    return (
        <div className="mt-8">
            <h2 className="text-2xl font-bold mb-4">
                Built-in Dataset
            </h2>

            <p className="text-sm opacity-70 mb-5">
                These documents are available automatically.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {builtInPDFs.map((pdf) => (
                    <div
                        key={pdf.file}
                        className="p-4 rounded-xl border border-white/10 bg-white/5"
                    >
                        <h3 className="font-semibold mb-3">
                            {pdf.name}
                        </h3>

                        <a
                            href={`/datasets/${pdf.file}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-block px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700"
                        >
                            Open PDF
                        </a>
                    </div>
                ))}
            </div>
        </div>
    );
}