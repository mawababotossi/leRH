from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.core.credits import SUBSCRIPTION_BONUS
from leRH.db.models import Message, Subscription, User
from leRH.db.repository import SubscriptionRepository

DEFAULT_MIN_MATCH_SCORE = 60.0


def onboarding_capabilities_text() -> str:
    return (
        "Ton profil est prêt.\n\n"
        "Voici ce que je peux faire pour toi :\n"
        "1. Chercher des offres adaptées à ton profil\n"
        "2. Générer un CV adapté à une offre (5 crédits)\n"
        "3. Générer une lettre de motivation (3 crédits)\n"
        "4. T'envoyer des notifications quand de nouvelles offres matchent ton profil\n\n"
        "Commandes utiles :\n"
        "/statut - profil, crédits et abonnement\n"
        "/notifications - activer ou consulter les alertes emploi\n"
        "/profil - voir tes informations de profil"
    )


def _skills_text(user: User) -> str:
    if not user.skills:
        return "-"
    if isinstance(user.skills, list):
        return ", ".join(str(skill) for skill in user.skills[:8]) or "-"
    return str(user.skills)


def _subscription_summary(subscription: Subscription | None) -> str:
    if not subscription:
        return "Non activé"
    status = "actif" if subscription.active else "désactivé"
    channels = []
    if subscription.notify_whatsapp:
        channels.append("WhatsApp")
    if subscription.notify_telegram:
        channels.append("Telegram")
    channel_text = ", ".join(channels) if channels else "aucun canal"
    return f"{status}, score minimum {subscription.min_match_score:.0f}/100, canal: {channel_text}"


async def build_status_text(session: AsyncSession, user: User) -> str:
    subscription = await SubscriptionRepository(session).get_by_user(user.id)
    return (
        "Statut du compte\n\n"
        f"Nom : {user.name or '-'}\n"
        f"Pays : {user.country or '-'}\n"
        f"Activité : {user.activity or '-'}\n"
        f"Diplôme : {user.diploma or '-'}\n"
        f"Compétences : {_skills_text(user)}\n"
        f"Crédits restants : {user.credits or 0}\n"
        f"Notifications : {_subscription_summary(subscription)}"
    )


async def build_notifications_text(
    session: AsyncSession,
    user: User,
    *,
    platform: str,
    activate: bool = True,
) -> str:
    repo = SubscriptionRepository(session)
    subscription = await repo.get_by_user(user.id)
    created = False

    if activate:
        if subscription:
            subscription.active = True
            subscription.min_match_score = subscription.min_match_score or DEFAULT_MIN_MATCH_SCORE
        else:
            subscription = await repo.create(
                user_id=user.id,
                active=True,
                min_match_score=DEFAULT_MIN_MATCH_SCORE,
                notify_telegram=platform == "telegram",
                notify_whatsapp=platform == "whatsapp",
            )
            created = True

        if platform == "telegram":
            subscription.notify_telegram = True
        elif platform == "whatsapp":
            subscription.notify_whatsapp = True

    if created:
        from leRH.core.credits import CreditManager

        await CreditManager().add(
            user.id,
            SUBSCRIPTION_BONUS,
            reason="subscription_bonus",
            session=session,
        )
        bonus_text = f"\n\nBonus ajouté : {SUBSCRIPTION_BONUS} crédits."
    else:
        bonus_text = ""

    return (
        "Notifications emploi\n\n"
        f"État : {_subscription_summary(subscription)}\n"
        "Tu recevras les nouvelles offres qui dépassent ton score minimum de matching. "
        "Chaque notification envoyée coûte 1 crédit."
        f"{bonus_text}"
    )


async def maybe_subscription_prompt(session: AsyncSession, user: User) -> str:
    subscription = await SubscriptionRepository(session).get_by_user(user.id)
    if subscription and subscription.active:
        return ""

    message_count = await session.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.user_id == user.id, Message.role == "user")
    )
    if not message_count or message_count < 3 or message_count % 4 != 0:
        return ""

    return (
        "\n\nAstuce : tu peux activer les alertes emploi avec /notifications. "
        f"C'est gratuit à l'activation et ça ajoute {SUBSCRIPTION_BONUS} crédits bonus."
    )
