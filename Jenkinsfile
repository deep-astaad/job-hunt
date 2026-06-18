pipeline {
  agent any

  options {
    disableConcurrentBuilds()
    timestamps()
  }

  environment {
    IMAGE_NAME    = 'ghcr.io/harsh-upadhayay/job-hunt'
    FRONTEND_IMAGE = 'ghcr.io/harsh-upadhayay/job-hunt-frontend'
  }

  stages {
    stage('Build images') {
      parallel {
        stage('Backend') {
          steps {
            sh '''
              set -eu
              docker build \
                --tag "$IMAGE_NAME:$GIT_COMMIT" \
                --tag "$IMAGE_NAME:main" \
                .
            '''
          }
        }
        stage('Frontend') {
          steps {
            sh '''
              set -eu
              docker build \
                --target runner \
                --tag "$FRONTEND_IMAGE:$GIT_COMMIT" \
                --tag "$FRONTEND_IMAGE:main" \
                frontend/
            '''
          }
        }
      }
    }

    stage('Smoke check') {
      steps {
        sh '''
          set -eu
          docker run --rm \
            -e APIFY_API_TOKEN=dummy \
            -e OPENAI_API_KEY=dummy \
            --entrypoint python \
            "$IMAGE_NAME:$GIT_COMMIT" \
            backend/manage.py check
        '''
      }
    }

    stage('Publish images') {
      when {
        expression {
          env.BRANCH_NAME == 'main' || env.GIT_BRANCH == 'main' || env.GIT_BRANCH == 'origin/main'
        }
      }
      steps {
        withCredentials([usernamePassword(
          credentialsId: 'ghcr_access_hu',
          usernameVariable: 'GHCR_USER',
          passwordVariable: 'GHCR_TOKEN'
        )]) {
          sh '''
            set -eu
            echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
            docker push "$IMAGE_NAME:$GIT_COMMIT"
            docker push "$IMAGE_NAME:main"
            docker push "$FRONTEND_IMAGE:$GIT_COMMIT"
            docker push "$FRONTEND_IMAGE:main"
            docker logout ghcr.io
          '''
        }
      }
    }
  }
}
