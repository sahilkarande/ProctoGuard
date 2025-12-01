from models import Question, db
Question.query.delete()
db.session.commit()
print("✅ All old questions deleted")