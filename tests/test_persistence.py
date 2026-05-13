import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from leRH.db.base import async_session_factory
from leRH.db.repository import JobRepository
from leRH.core.assistants.manager import Assistant

async def test_web_persistence():
    async with async_session_factory() as db:
        # 1. Simuler une recherche web via l'assistant
        assistant = Assistant(
            name="TestUser",
            country="Togo",
            activity="Developer",
            db_session=db
        )
        
        # Simuler un appel à search_web_jobs
        tool_call = type('obj', (object,), {
            'function': type('obj', (object,), {
                'name': 'search_web_jobs',
                'arguments': '{"query": "Python Developer Lomé"}'
            })
        })
        
        print("\n--- Test: Recherche Web ---")
        reply_json = await assistant._handle_tool_call(tool_call)
        results = json.loads(reply_json)
        
        assert len(results) > 0
        job_id = results[0]["id"]
        print(f"Offre persistée avec ID: {job_id}")
        
        # 2. Vérifier que l'offre est bien en base
        repo = JobRepository(db)
        job = await repo.get_by_id(job_id)
        assert job is not None
        assert job.is_external is True
        print(f"Vérification DB réussie pour: {job.title}")
        
        # 3. Simuler une demande de CV avec cet ID
        tool_call_cv = type('obj', (object,), {
            'function': type('obj', (object,), {
                'name': 'generate_cv',
                'arguments': f'{{"job_id": "{job_id}", "confirmed": true}}'
            })
        })
        
        print("\n--- Test: Génération CV via ID ---")
        # On ne lance pas la tâche de fond réelle ici pour éviter d'appeler l'API OpenAI
        # On vérifie juste que le handler trouve bien le job et passe l'étape de validation
        reply_cv = await assistant._handle_tool_call(tool_call_cv)
        print(f"Réponse handler CV: {reply_cv}")
        assert "success" in reply_cv or "confirmation_required" in reply_cv

if __name__ == "__main__":
    import json
    asyncio.run(test_web_persistence())
