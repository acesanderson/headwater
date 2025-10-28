from siphon.database.postgres.PGRES_processed_content import get_all_siphon


ss = get_all_siphon()

# Assemble a list of objects from ss by a few different categories of wordcount of s.context: 500, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000
datasets = {
    500: [],
    1000: [],
    2000: [],
    3000: [],
    5000: [],
    7500: [],
    10000: [],
}

for s in ss:
    wordcount = len(s.context.split())
    for category in datasets.keys():
        if wordcount <= category:
            d = {
                "sourcetype": s.llm_context.sourcetype,
                "context": s.context,
                "gold_standard": s.summary,
            }
            datasets[category].append(d)
            break
