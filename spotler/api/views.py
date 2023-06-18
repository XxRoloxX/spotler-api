import io
import json
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import mixins
from rest_framework import generics
from rest_framework.parsers import JSONParser
from rest_framework import status
from django import http

from .session_validation.session_validation import (
    create_spotify_wrapper_from_session,
    verify_cookies_correctness,
)
from .classification.classifier_loader import ClassifiersLoader
from .data_collection.data_clean_up import fit_data_to_lda, get_most_popular_genres
from .data_collection.save_to_db import save_track_to_db
from .serializers import TrackFeaturesSerializer, TrackSerializer
from .models import Track, Genre
from .spotify_wrapper.spotify_wrapper import SpotifyWrapper
from .classification.classifier_trainer import ClassifierTrainer, GenreClassifierTrainer

# Create your views here.


ACTIVE_CLASSIFIERS = ClassifiersLoader()


@api_view(["POST"])
def retrieve_tracks_from_playlist(request):
    """
    Add tracks from a playlist to the database
    """
    spotify_wrapper = SpotifyWrapper(
        code=request.session.get("code"),
        refresh_token=request.session.get("refresh_token"),
    )
    if "playlist_id" not in request.data:
        return Response(status=status.HTTP_400_BAD_REQUEST)

    playlist_id = request.data["playlist_id"]

    tracks_data = [
        {
            "track_id": track["track"]["id"],
            "name": track["track"]["name"],
            "artists": track["track"]["artists"],
        }
        for track in spotify_wrapper.getTracks(playlist_id)["items"]
    ]

    response_list = []

    for track_item in tracks_data:
        response_list.append(save_track_to_db(track_item, spotify_wrapper))

    return Response(response_list)


# @api_view(["GET"])
# def cluster_genres_with_simplified_names(request, pk=None, *args, **kwargs):
#     def find_simplified_genre(current_genre: str, list_of_popular_genres: list):
#         for popular_genre in list_of_popular_genres:
#             if popular_genre[0] in current_genre:
#                 return popular_genre[0]
#         return None

#     number_of_classes = (
#         0.1 if not request.GET.get("classes") else int(request.GET.get("classes"))
#     )

#     most_popular_genres = get_most_popular_genres(number_of_classes, "db.sqlite3")
#     print(most_popular_genres)

#     genres = Genre.objects.all()

#     for genre in genres:
#         simplified_genre = find_simplified_genre(genre.name, most_popular_genres)
#         genre.simplyfied_name = simplified_genre
#         genre.save()

#     return Response(most_popular_genres)


# @api_view(["GET"])
# def fit_model(request, pk=None, *args, **kwargs):
#     criteria = (
#         0.1 if not request.GET.get("criteria") else float(request.GET.get("criteria"))
#     )
#     correctnes = fit_data_to_lda("db.sqlite3", criteria)
#     return Response(correctnes)


@api_view(["GET"])
def train_model(request, pk=None, *args, **kwargs):
    """
    Train the model with the given criteria.
    """
    genre_classifier = GenreClassifierTrainer()
    genre_classifier.create_source_dataframe()
    genre_classifier.resample_set("LexicalUndersampling", 20)
    train_result = genre_classifier.train_model(request.GET.get("classifier"))
    return Response(train_result)


@api_view(["GET"])
def track_genres(request):
    """
    Return a list of all the genres in the database in relation to the track.
    """

    spotler_wrapper = SpotifyWrapper(
        code=request.session["code"], refresh_token=request.session["refresh_token"]
    )

    track_id = request.GET.get("track_id")
    track_features = spotler_wrapper.getTrackFeatures(track_id)
    track_features_serializer = TrackFeaturesSerializer(data=track_features)

    if track_features_serializer.is_valid():
        active_classifier = ACTIVE_CLASSIFIERS.get_classifier_trainer(0)["model"]
        return Response(
            active_classifier.predict_proba_with_classes(
                track_features_serializer.validated_data
            )
        )
    


    return Response({"status": track_features}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
def authorize_with_spotify(request):
    """
    Authorize the user with spotify and return the response back to the client.
    """
    spotler_wrapper = SpotifyWrapper()

    if "code" not in request.data:
        return Response(
            {"status": "error", "message": "No code in request"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    spotler_wrapper.code = request.data["code"]
    response = spotler_wrapper.get_refresh_token()

    if "error" in response:
        return Response(
            {"error": response["error"]}, status=status.HTTP_401_UNAUTHORIZED
        )

    request.session["code"] = spotler_wrapper.code
    request.session["refresh_token"] = spotler_wrapper.refresh_token

    return Response({"status": "Authorized successfully"}, status=status.HTTP_200_OK)


@api_view(["GET"])
def verify_cookies(request):
    """
    Verify clients cookies and return the response back to the client.
    """

    if "code" not in request.session or "refresh_token" not in request.session:
        return Response({"cookie_status": False})

    spotify_wrapper = SpotifyWrapper(
        code=request.session["code"], refresh_token=request.session["refresh_token"]
    )
    response_status = spotify_wrapper.get_new_access_token()
    if "error" in response_status:
        return Response({"cookie_status": False})

    return Response({"cookie_status": True})


@api_view(["GET"])
def search_tracks(request):

    track_name = request.GET.get("track_name")

    if not track_name:
        return Response(
            {"status": "error", "message": "No track name in request"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    validated_spotify_wrapper = create_spotify_wrapper_from_session(request.session)

    if not validated_spotify_wrapper:
        return Response(
            {"status": "error", "message": "Invalid cookies"},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    
    searched_tracks = validated_spotify_wrapper.simplified_tracks_search(track_name)

    return Response(searched_tracks)

@api_view(["GET"])
def profile_info(request):
    spotify_wrapper = create_spotify_wrapper_from_session(request.session)

    if not spotify_wrapper:
        return Response(
            {"status": "error", "message": "Invalid cookies"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    result = spotify_wrapper.get_profile_info()

    return Response(result)
@api_view(["PUT"])
def delete_cookies(request):
    """ Delete the cookies from the session."""
    request.session["code"]= None
    request.session["refresh_token"] = None
    return Response({"status": "ok"})