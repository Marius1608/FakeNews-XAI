/* examples.ts — ready-to-run articles for the Analyze tab (demo / first visit) */

export interface ExampleArticle {
  id: string;
  label: string;
  hint: string;
  title: string;
  publication_date: string;
  text: string;
}

export const EXAMPLE_ARTICLES: ExampleArticle[] = [
  {
    id: "inconsistent",
    label: "With inconsistencies",
    hint: "Obama signing a law in 2005 — before his term",
    title: "Obama returns to Capitol Hill",
    publication_date: "2024-03-12",
    text:
      "WASHINGTON — Former President Barack Obama returned to Capitol Hill on Tuesday to speak about health care reform. " +
      "In his remarks, he recalled signing the Affordable Care Act into law in 2005, during his first year in the White House. " +
      "Obama served as President of the United States from 2009 to 2017, after defeating John McCain in the 2008 election. " +
      "His successor, Donald Trump, took office in January 2017. " +
      "Obama also praised Joe Biden, who served as his Vice President and later became President in 2021. " +
      "Earlier in his career, Obama was elected to the U.S. Senate from Illinois in 2004.",
  },
  {
    id: "consistent",
    label: "Consistent",
    hint: "European leaders, all dates correct",
    title: "European leadership changes",
    publication_date: "2023-01-15",
    text:
      "Angela Merkel served as Chancellor of Germany from 2005 to 2021. " +
      "She was succeeded by Olaf Scholz, who took office in December 2021. " +
      "Before becoming Chancellor, Merkel led the Christian Democratic Union, which she chaired from 2000 to 2018. " +
      "Emmanuel Macron became President of France in 2017 and was re-elected in 2022.",
  },
  {
    id: "no-dates",
    label: "No temporal facts",
    hint: "Nothing to verify — shows the empty case",
    title: "Budget debate continues",
    publication_date: "",
    text:
      "Lawmakers continued to debate the proposed budget on Thursday. " +
      "Several members of the committee raised concerns about infrastructure spending, " +
      "while others argued that the plan did not go far enough on education. A vote is expected soon.",
  },
];
