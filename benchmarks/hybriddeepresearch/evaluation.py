"""Host-side evaluation schemas and scoring contracts; never solver input."""

def evaluation_rows(tasks, predicted):
    sql, text = [], []
    for task in tasks:
        common = dict(instance_id=task.id, response=predicted[task.id]["final_answer"])
        if task.category == "search_to_sql":
            gold = task.reference.get("sql")
            if not isinstance(gold, str) or not gold.strip():
                raise ValueError("Missing gold SQL; use the full release for host-side evaluation")
            sql.append(dict(common, db=task.db, gold_sql=gold))
        else:
            gold = task.reference.get("final_answer")
            if gold is None:
                raise ValueError("Missing gold answer")
            text.append(dict(common, question=task.reference["final_question"], correct_answer=gold))
    return dict(s2sql=sql, text=text)
